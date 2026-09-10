import unittest
from datetime import date
from meeting_os.due_dates import suggest_due, suggestions_for_tasks

A = date(2026, 9, 9)   # Wednesday


class DueDateTests(unittest.TestCase):
    def test_relative_expressions(self):
        cases = {'yarın': '2026-09-10', 'öbür gün': '2026-09-11', 'bugün': '2026-09-09', 'haftaya salı': '2026-09-15', 'salıya kadar': '2026-09-15',
                 'bu cuma': '2026-09-11', 'cuma günü': '2026-09-11', 'çarşamba': '2026-09-16', 'haftaya': '2026-09-16', 'ay sonu': '2026-09-30',
                 'hafta sonu': '2026-09-12', '3 gün içinde': '2026-09-12', 'iki hafta içinde': '2026-09-23', '15 eylül': '2026-09-15', "ayın 20'sine kadar": '2026-09-20',
                 '5 ocak': '2027-01-05', 'gelecek ay': '2026-10-09', 'bu hafta': '2026-09-11'}
        for text, expected in cases.items():
            with self.subTest(text=text): self.assertEqual(suggest_due(text, A), date.fromisoformat(expected))
    def test_unclear_gives_none(self):
        for text in ['', 'en kısa zamanda', 'sonra', 'ürün çıkınca', 'belki', 'Q4']:
            with self.subTest(text=text): self.assertIsNone(suggest_due(text, A))
    def test_task_proposals_skip_done_and_confirmed(self):
        tasks = [{'id': 'a', 'title': 'Rapor', 'due_text': 'yarın', 'created': '2026-09-09T10:00:00+00:00', 'state': 'open', 'payload': {}},
                 {'id': 'b', 'title': 'Bitti', 'due_text': 'yarın', 'created': '2026-09-09T10:00:00+00:00', 'state': 'done', 'payload': {}},
                 {'id': 'c', 'title': 'Onaylı', 'due_text': 'yarın', 'created': '2026-09-09T10:00:00+00:00', 'state': 'open', 'payload': {'due_date': '2026-09-12'}},
                 {'id': 'd', 'title': 'Belirsiz', 'due_text': 'en kısa zamanda', 'created': '2026-09-09T10:00:00+00:00', 'state': 'open', 'payload': {}}]
        self.assertEqual([p['task'] for p in suggestions_for_tasks(tasks)], ['a'])
        self.assertEqual(suggestions_for_tasks(tasks)[0]['suggested'], '2026-09-10')


class DueDateBridgeTests(unittest.TestCase):
    def test_intelligence_carries_suggestions_and_set_due_persists(self):
        import tempfile, json
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.memory import Memory
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'m.sqlite'; s=Store(db); mid=s.create_meeting('Sprint',{}); s.status(mid,'complete')
            with s.db: s.db.execute("UPDATE meetings SET created='2026-09-09T12:00:00+00:00' WHERE id=?",(mid,))   # "yarın" is counted from the day of the MEETING
            mem=Memory(s)
            with mem.db: mem.db.execute("INSERT INTO tasks(id,meeting,analysis,input_hash,title,owner,due_text,state,payload,user_edited,created,updated) VALUES('t1',?,NULL,'h','Rapor','Ayşe','yarın','open','{}',0,'2026-09-09T10:00:00+00:00','2026-09-09T10:00:00+00:00')",(mid,))
            s.close()
            r=dispatch({'action':'intelligence','meeting':mid},db)
            self.assertEqual(r['due_suggestions'][0]['suggested'],'2026-09-10')
            self.assertEqual(dispatch({'action':'task_set_due','task':'t1','due_date':'2026-09-10'},db),{'due_date':'2026-09-10'})
            r=dispatch({'action':'intelligence','meeting':mid},db)
            self.assertEqual(r['tasks'][0]['payload']['due_date'],'2026-09-10'); self.assertEqual(r['due_suggestions'],[])
            self.assertEqual(dispatch({'action':'task_set_due','task':'t1','due_date':None},db),{'due_date':None})


class MeetingDayAnchorTests(unittest.TestCase):
    """The task row's `created` is the moment the ANALYSIS was saved, in UTC. A meeting recorded just after
    midnight local time was analysed on the previous UTC day, and every "yarın" came out one day early."""
    def test_the_anchor_is_the_meetings_local_day(self):
        from datetime import datetime, timedelta, timezone
        from meeting_os.insights import local_day
        created = '2026-09-13T21:30:00+00:00'   # 14 Eylül 00:30 in Istanbul
        day = local_day(created)
        tasks = [{'id': 'a', 'meeting': 'm', 'title': 'Rapor', 'due_text': 'yarın', 'created': created, 'state': 'open', 'payload': {}}]
        out = suggestions_for_tasks(tasks, {'m': day})
        self.assertEqual(out[0]['anchor'], day.isoformat())
        self.assertEqual(out[0]['suggested'], (day + timedelta(days=1)).isoformat())
        utc_day = datetime.fromisoformat(created).astimezone(timezone.utc).date()
        if day != utc_day:   # only provable where the Mac is not on UTC; the anchor above is checked either way
            self.assertNotEqual(out[0]['suggested'], (utc_day + timedelta(days=1)).isoformat())

    def test_without_an_anchor_the_local_day_of_the_task_is_used(self):
        from meeting_os.insights import local_day
        created = '2026-09-09T10:00:00+00:00'
        tasks = [{'id': 'a', 'meeting': 'm', 'title': 'Rapor', 'due_text': 'bugün', 'created': created, 'state': 'open', 'payload': {}}]
        self.assertEqual(suggestions_for_tasks(tasks)[0]['suggested'], local_day(created).isoformat())

    def test_a_retired_task_gets_no_proposal(self):
        tasks = [{'id': 'a', 'title': 'Rapor', 'due_text': 'yarın', 'created': '2026-09-09T10:00:00+00:00', 'state': 'superseded', 'payload': {}}]
        self.assertEqual(suggestions_for_tasks(tasks), [])

    def test_a_suggestion_the_day_has_already_passed_says_so(self):
        from datetime import date as _date
        tasks = [{'id': 'a', 'meeting': 'm', 'title': 'Rapor', 'due_text': 'yarın', 'created': '2026-09-09T10:00:00+00:00', 'state': 'open', 'payload': {}}]
        past = suggestions_for_tasks(tasks, {'m': A}, today=_date(2026, 10, 1))
        self.assertEqual((past[0]['suggested'], past[0]['past']), ('2026-09-10', True))
        ahead = suggestions_for_tasks(tasks, {'m': A}, today=A)
        self.assertEqual((ahead[0]['suggested'], ahead[0]['past']), ('2026-09-10', False))
        self.assertFalse(suggestions_for_tasks(tasks, {'m': A}, today=_date(2026, 9, 10))[0]['past'])   # today is not past
