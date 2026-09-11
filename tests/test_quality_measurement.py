"""1.2.82 — repeatable measurement: the daily numbers, the fleet trend, the report that stopped double
counting, the time-ordered identity replay and the real-size fixture generator.

Nothing here changes a model or a threshold; every test is about what the app can HONESTLY say about itself.
"""
import json,subprocess,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from meeting_os import quality,reports
from meeting_os.memory import Memory
from meeting_os.store import Store
from meeting_os.types import Segment

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/fixtures/analysis'
FLAGS=['cloud_transcript','cloud_diarization']
THERM='Note: No thermal warning level has been recorded\nCPU_Speed_Limit \t= 70\n'


def fake_run(cmd,**kwargs):
    if cmd[0].endswith('pmset'): return SimpleNamespace(returncode=0,stdout=THERM,stderr='')
    return SimpleNamespace(returncode=0,stdout='Test-Mac\n',stderr='')


def today():
    return datetime.now().astimezone().date()


def analysis_payload(sid,bullets=2,seconds=12.5):
    return {'summary':[{'text':f'Konu {i}','evidence':[{'segment_id':sid,'quote':'konu','start':0,'speaker':'Ayşe'}]} for i in range(bullets)],
            'decisions':[],'risks':[],'questions':[],
            'actions':[{'title':'Raporu çıkarmak','owner':'Ayşe','due_text':'yarın','evidence':[{'segment_id':sid,'quote':'rapor','start':0,'speaker':'Ayşe'}]}],
            'elapsed_seconds':seconds}


class DailySummaryTests(unittest.TestCase):
    """The numbers a day of use produces, each with the scope it was measured in."""

    def build(self,tmp):
        data=Path(tmp);store=Store(data/'meeting-os.sqlite')
        mid=store.create_meeting('Gün',{'model':'m'})
        a=store.add_segment(mid,Segment(0,10,'Kavak ekibi bugün devam etti','system','Konuşmacı 1',
                                        metrics={'cluster':'0:0','identity':{'name':'Ayşe'}},flags=FLAGS))
        store.add_segment(mid,Segment(10,20,'Tamam','system','Konuşmacı 2',
                                      metrics={'cluster':'0:1','identity':{'name':'Mehmet'}},flags=FLAGS))
        store.status(mid,'complete')
        return data,store,mid,a

    def test_names_are_reviewed_falsified_or_untouched_and_untouched_is_never_a_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,store,mid,_=self.build(tmp)
            store.correct(mid,'Konuşmacı 1','Ali')      # the automatic name was overruled
            record=quality.daily_summary(store,data,version='1.2.82')
            m=record['metrics']
            self.assertEqual((m['names_reviewed']['n'],m['names_reviewed']['d']),(1,2))
            self.assertEqual((m['names_falsified']['n'],m['names_falsified']['d']),(1,1))
            self.assertEqual((m['names_unreviewed']['n'],m['names_unreviewed']['d']),(1,2))   # Mehmet was never judged
            self.assertEqual(m['names_falsified']['rate'],1.0)
            store.close()

    def test_an_empty_denominator_is_null_and_never_a_zero_percent_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            record=quality.daily_summary(store,data)
            for key,value in record['metrics'].items():
                self.assertEqual(value['d'],0,key);self.assertIsNone(value['rate'],key)
            self.assertEqual(record['meetings'],0)
            self.assertIsNone(record['analysis_seconds']['p50'])
            store.close()

    def test_a_taught_word_that_comes_back_wrong_in_a_later_raw_transcript_is_counted_once_per_meeting(self):
        with tempfile.TemporaryDirectory() as tmp:
            from meeting_os.correction_memory import _ensure_taught
            data,store,mid,_=self.build(tmp)
            _ensure_taught(store)
            earlier=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
            with store.db:
                store.db.execute('INSERT INTO taught_words(original,display,replacement,count,meetings,created,vocabulary_added) VALUES(?,?,?,?,?,?,0)',
                                 ('kavak','Kavak','Kavağ',1,'[]',earlier))
                store.db.execute('INSERT INTO taught_words(original,display,replacement,count,meetings,created,vocabulary_added) VALUES(?,?,?,?,?,?,0)',
                                 ('zeytin','Zeytin','Zeytin',1,'[]',earlier))
            m=quality.daily_summary(store,data)['metrics']['word_repeat_errors']
            self.assertEqual((m['n'],m['d']),(1,2))   # "Kavak" is still in the raw text; "Zeytin" never came up
            store.close()

    def test_a_word_taught_after_the_meeting_is_not_counted_against_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            from meeting_os.correction_memory import _ensure_taught
            data,store,mid,_=self.build(tmp)
            _ensure_taught(store)
            later=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
            with store.db:
                store.db.execute('INSERT INTO taught_words(original,display,replacement,count,meetings,created,vocabulary_added) VALUES(?,?,?,?,?,?,0)',
                                 ('kavak','Kavak','Kavağ',1,'[]',later))
            m=quality.daily_summary(store,data)['metrics']['word_repeat_errors']
            self.assertEqual((m['n'],m['d']),(0,0))
            store.close()

    def test_analysis_seconds_and_task_edits_come_from_the_day_that_produced_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,store,mid,sid=self.build(tmp)
            memory=Memory(store)
            memory.save_analysis(mid,memory.current_hash(mid),'test-model',analysis_payload(sid,bullets=3,seconds=41.0))
            task=memory.actions()[0]
            memory.update_action(task['id'],{'owner':'Mehmet'})
            record=quality.daily_summary(store,data)
            m=record['metrics']
            self.assertEqual((m['meetings_analysed']['n'],m['meetings_analysed']['d']),(1,1))
            self.assertEqual((m['task_edits']['n'],m['task_edits']['d']),(1,1))
            self.assertEqual(record['analysis_seconds'],{'p50':41.0,'p95':41.0,'n':1})
            self.assertEqual((m['summary_edits']['n'],m['summary_edits']['d']),(0,3))   # 1.2.80's insight_edits exists: three items shown, none edited
            store.close()

    def test_the_record_is_replaced_by_key_not_added_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,store,mid,_=self.build(tmp)
            first=quality.daily_summary(store,data,version='1.2.82',device='dev-1')
            store.correct(mid,'Konuşmacı 1','Ali')
            second=quality.daily_summary(store,data,version='1.2.82',device='dev-1')
            stored=quality.load_daily(data)
            self.assertEqual(len(stored),1)
            self.assertEqual(quality.daily_key(first),quality.daily_key(second))
            self.assertEqual(list(stored.values())[0]['metrics']['names_reviewed']['n'],1)   # the newer measurement won
            other=quality.daily_summary(store,data,version='1.2.83',device='dev-1')
            self.assertEqual(len(quality.load_daily(data)),2)   # a different app version is a different measurement
            self.assertNotEqual(quality.daily_key(first),quality.daily_key(other))
            store.close()

    def test_the_record_carries_no_text_no_name_and_no_meeting_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,store,mid,_=self.build(tmp)
            store.correct(mid,'Konuşmacı 1','Ali')
            blob=json.dumps(quality.daily_summary(store,data,version='1.2.82'),ensure_ascii=False)
            for secret in ('Ali','Ayşe','Mehmet','Kavak','Gün',mid): self.assertNotIn(secret,blob)
            store.close()


class WordRepeatTests(unittest.TestCase):
    """Per word: how often a later RAW transcript wrote the old spelling again, and whether the rule caught it.

    The daily summary pools this into one rate; the per-word numbers are what Ayarlar → Sesler ve sözlük shows
    and they never leave this Mac."""

    def taught(self,store,original,replacement,days=2):
        from meeting_os.correction_memory import _ensure_taught,_fold
        _ensure_taught(store)
        created=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        with store.db:
            store.db.execute('INSERT INTO taught_words(original,display,replacement,count,meetings,created,vocabulary_added) VALUES(?,?,?,?,?,?,0)',
                             (_fold(original),original,replacement,1,'[]',created))

    def meeting(self,store,title,text,apply=False):
        mid=store.create_meeting(title,{'model':'m'})
        store.add_segment(mid,Segment(0,5,text,'system','Konuşmacı 1',flags=FLAGS))
        if apply:
            from meeting_os import correction_memory as cm
            cm.apply_rules(store,mid)
        store.status(mid,'complete')
        return mid

    def test_a_repeat_is_counted_once_per_meeting_and_split_by_what_the_user_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'meeting-os.sqlite')
            self.taught(store,'Spilendo','Splendo')
            self.taught(store,'Trendyoll','Trendyol')
            self.meeting(store,'düzeltildi','Spilendo demosu ve yine Spilendo.',apply=True)   # raw wrong, final fixed
            self.meeting(store,'düzeltilmedi','Spilendo toplantısı.')                         # raw wrong, final still wrong
            self.meeting(store,'temiz','Başka bir konu.')
            result=quality.word_repeat_errors(store)
            words={w['original']:w for w in result['words']}
            self.assertEqual((words['Spilendo']['repeats'],words['Spilendo']['fixed'],words['Spilendo']['unfixed']),(2,1,1))
            self.assertEqual(words['Spilendo']['checks'],3)      # three later meetings could have gone wrong
            self.assertEqual((words['Trendyoll']['repeats'],words['Trendyoll']['checks']),(0,3))
            self.assertEqual((result['hits'],result['checks']),(2,6))
            self.assertEqual(result['rate']['n'],2)
            self.assertEqual(quality.daily_summary(store,Path(tmp),save=False)['metrics']['word_repeat_errors']['n'],2)
            store.close()

    def test_a_meeting_older_than_the_rule_is_not_evidence_about_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'meeting-os.sqlite')
            self.meeting(store,'önce','Spilendo demosu.')
            self.taught(store,'Spilendo','Splendo',days=0)   # taught now: the meeting above predates it
            result=quality.word_repeat_errors(store)
            self.assertEqual((result['words'][0]['checks'],result['words'][0]['repeats']),(0,0))
            self.assertIsNone(result['rate']['rate'])
            store.close()

    def test_with_nothing_taught_there_is_no_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'meeting-os.sqlite')
            self.meeting(store,'a','Bir cümle.')
            self.assertEqual(quality.word_repeat_errors(store)['words'],[])
            self.assertIsNone(quality.word_repeat_errors(store)['rate']['rate'])
            store.close()

    def test_the_settings_list_carries_the_counts_and_no_other_mac_does(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'meeting-os.sqlite';store=Store(path)
            self.taught(store,'Spilendo','Splendo')
            self.meeting(store,'düzeltildi','Spilendo demosu.',apply=True)
            store.close()
            row=next(r for r in dispatch({'action':'word_rules'},path)['rules'] if r['original']=='Spilendo')
            self.assertEqual((row['repeats'],row['repeats_fixed'],row['repeats_unfixed']),(1,1,0))
            report=quality.daily_summary(Store(path),Path(tmp),save=False)
            self.assertNotIn('Spilendo',json.dumps(report,ensure_ascii=False))   # the aggregate carries no word


class ReplayRulesTests(unittest.TestCase):
    """Would TODAY's rules produce the text the user kept? Synthetic pairs, no database needed."""

    RULES=[{'original':'Spilendo','replacement':'Splendo','source':'taught'}]

    def test_matches_mismatches_and_pairs_todays_rules_do_not_touch(self):
        pairs=[{'meeting':'m1','segment':1,'raw':'Spilendo demosu.','final':'Splendo demosu.','was':['Spilendo']},
               {'meeting':'m1','segment':2,'raw':'Spilendo geldi.','final':'Splendo A.Ş. geldi.','was':['Spilendo']},
               {'meeting':'m2','segment':3,'raw':'Trendyoll ile.','final':'Trendyol ile.','was':['Trendyoll']}]
        result=quality.replay_rules(None,pairs=pairs,rules=self.RULES)
        self.assertEqual((result['pairs'],result['matched'],result['mismatched'],result['unchanged']),(3,1,2,1))
        rules={r['original']:r for r in result['by_rule']}
        self.assertEqual((rules['Spilendo']['applied'],rules['Spilendo']['matched'],rules['Spilendo']['mismatched']),(2,1,1))
        self.assertEqual(rules['Spilendo']['state'],'current')
        # A rule that only exists in the history is listed as retired with what it used to do, never as a match.
        self.assertEqual((rules['Trendyoll']['state'],rules['Trendyoll']['was_applied'],rules['Trendyoll']['applied']),('retired',1,0))
        self.assertEqual([m['segment'] for m in result['mismatches']],[2,3])

    def test_the_rule_set_has_a_version_that_moves_when_the_rules_do(self):
        from meeting_os import correction_memory as cm
        other=[{'original':'Spilendo','replacement':'Splendo A.Ş.','source':'taught'}]
        self.assertNotEqual(cm.rules_version(self.RULES),cm.rules_version(other))
        self.assertEqual(cm.rules_version(self.RULES),cm.rules_version(list(self.RULES)))
        self.assertEqual(cm.rules_version([]),'empty')
        self.assertEqual(quality.replay_rules(None,pairs=[],rules=self.RULES)['version'],cm.rules_version(self.RULES))

    def test_the_real_pairs_come_from_this_macs_own_segments_and_the_replay_writes_nothing(self):
        from meeting_os import correction_memory as cm
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'meeting-os.sqlite')
            mid=store.create_meeting('a',{'model':'m'})
            sid=store.add_segment(mid,Segment(0,5,'Spilendo demosu.','system','Konuşmacı 1',flags=FLAGS))
            store.correct_text(mid,sid,'Splendo demosu.')   # the user fixed it by hand: raw and final both kept
            store.status(mid,'complete')
            pairs=quality.rule_pairs(store)
            self.assertEqual([(p['raw'],p['final']) for p in pairs],[('Spilendo demosu.','Splendo demosu.')])
            before=store.segments(mid)[0]['text']
            result=quality.replay_rules(store,rules=self.RULES)
            self.assertEqual((result['pairs'],result['matched'],result['mismatched']),(1,1,0))
            self.assertEqual(store.segments(mid)[0]['text'],before)
            # `replay` uses the rule set this Mac really has. One hand edit is not a rule (two meetings are),
            # so today's rules leave the pair alone — an honest mismatch, not a match to celebrate.
            summary,full=quality.replay(store,Path(tmp),identity=False,text=True)
            self.assertEqual((summary['text']['rules']['pairs'],summary['text']['rules']['mismatched'],summary['text']['rules']['unchanged']),(1,1,1))
            self.assertEqual(full['text']['rules']['version'],cm.rules_version(cm.all_rules(store)))
            store.close()


class TrendTests(unittest.TestCase):
    """One alert, and only when the numbers can carry one."""

    def hosts(self,current,previous,*,device='dev-1',days=7):
        """A fleet whose two periods have the given (errors, observations), spread over `days` days each."""
        end=datetime.now().astimezone().date()
        records=[]
        for index,(n,d) in enumerate([previous,current]):
            per=max(1,days)
            for offset in range(per):
                day=end-timedelta(days=(days-1-offset)+(days if index==0 else 0))
                share_n=n//per+(1 if offset<n%per else 0);share_d=d//per+(1 if offset<d%per else 0)
                records.append({'day':day.isoformat(),'device':device,'app_version':'1.2.82','written':day.isoformat()+'T10:00:00+00:00',
                                'metrics':{'names_falsified':{'n':share_n,'d':share_d,'rate':None}}})
        return {'Mac-A':{'heartbeat':{'quality_daily':records}}}

    def test_a_thirty_percent_rise_with_enough_observations_is_one_alert(self):
        trend=quality.quality_trend(self.hosts(current=(14,40),previous=(8,40)))
        self.assertTrue(trend['eligible'])
        self.assertEqual(len(trend['alerts']),1)
        self.assertEqual(trend['alerts'][0]['key'],'quality_trend')
        self.assertIn('en çok düzeltilen',trend['alerts'][0]['line'])
        self.assertGreaterEqual(trend['change'],0.30)

    def test_fewer_than_twenty_observations_raises_nothing_however_bad_the_rate_looks(self):
        trend=quality.quality_trend(self.hosts(current=(8,10),previous=(1,10)))
        self.assertFalse(trend['eligible'])
        self.assertEqual(trend['alerts'],[])
        self.assertIn('en az 20 gözlem',quality.trend_line(trend))

    def test_a_rate_that_did_not_rise_enough_raises_nothing(self):
        trend=quality.quality_trend(self.hosts(current=(11,40),previous=(10,40)))
        self.assertTrue(trend['eligible']);self.assertEqual(trend['alerts'],[])

    def test_the_same_day_uploaded_twice_is_counted_once(self):
        hosts=self.hosts(current=(14,40),previous=(8,40))
        doubled={'Mac-A':hosts['Mac-A'],'Mac-A-again':{'heartbeat':{'quality_daily':list(hosts['Mac-A']['heartbeat']['quality_daily'])}}}
        once=quality.quality_trend(hosts);twice=quality.quality_trend(doubled)
        self.assertEqual(once['current'],twice['current'])
        self.assertEqual(len(quality.daily_records(doubled)),len(quality.daily_records(hosts)))

    def test_two_devices_are_two_measurements_not_one_replaced(self):
        a=self.hosts(current=(14,40),previous=(8,40),device='dev-1')
        b=self.hosts(current=(14,40),previous=(8,40),device='dev-2')
        merged={'Mac-A':a['Mac-A'],'Mac-B':b['Mac-A']}
        self.assertEqual(quality.quality_trend(merged)['current']['d'],2*quality.quality_trend(a)['current']['d'])

    def test_the_fleet_alert_list_carries_the_trend_line(self):
        hosts=self.hosts(current=(14,40),previous=(8,40))
        keys=[a['key'] for a in reports.alerts(hosts)]
        self.assertEqual(keys.count('quality_trend'),1)


class ReportDoubleCountingTests(unittest.TestCase):
    """A per-meeting report may only carry per-meeting numbers."""

    def meeting(self,store,title,clusters):
        mid=store.create_meeting(title,{'model':'m'});t=0
        for speaker,name in clusters:
            store.add_segment(mid,Segment(t,t+10,'konuşma','system',speaker,speaker_name=name,
                                          metrics={'cluster':f'0:{t//10}','identity':{'name':name}},flags=FLAGS));t+=10
        store.status(mid,'complete');return mid

    def test_two_reports_from_one_host_do_not_double_the_database_wide_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            first=self.meeting(store,'Bir',[('K1','Ayşe'),('K2','Mehmet')])
            second=self.meeting(store,'İki',[('K1','Ayşe')])
            from meeting_os.quality import identity_report
            self.assertEqual(identity_report(store)['clusters'],3)          # the whole database
            self.assertEqual(identity_report(store,first)['clusters'],2)    # this meeting only
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                reports.write_meeting_report(store,first,data);reports.write_meeting_report(store,second,data)
                summary=reports.summarize(str(data/'shared'))
            identity=summary['hosts']['Test-Mac']['identity']
            self.assertEqual(identity['meetings'],2)
            self.assertEqual(identity['clusters'],3)          # 2 + 1, not 3 + 3
            self.assertEqual(identity['snapshots_skipped'],0)
            for row in summary['reports']: self.assertEqual(row['scorecard']['scope'],'meeting')
            store.close()

    def test_a_database_wide_scorecard_from_an_older_report_is_skipped_not_added(self):
        rows=[{'host':'Mac-Eski','scorecard':{'clusters':9,'auto_correct':4,'auto_wrong':1,'suggestion_confirmed':0,
                                              'suggestion_rejected':0,'missed_known':0,'still_unnamed':4,'snapshot':True,'scope':'database'}},
              {'host':'Mac-Eski','scorecard':{'clusters':9,'auto_correct':4,'auto_wrong':1,'suggestion_confirmed':0,
                                              'suggestion_rejected':0,'missed_known':0,'still_unnamed':4}},   # 1.2.81 and earlier: no scope at all
              {'host':'Mac-Eski','scorecard':{'clusters':2,'auto_correct':1,'auto_wrong':1,'suggestion_confirmed':0,
                                              'suggestion_rejected':0,'missed_known':0,'still_unnamed':0,'scope':'meeting','snapshot':False}}]
        aggregate=reports.add_scorecards(rows)['Mac-Eski']
        self.assertEqual((aggregate['clusters'],aggregate['meetings'],aggregate['snapshots_skipped']),(2,1,2))
        self.assertEqual(aggregate['auto_precision'],0.5)


class HeartbeatQualityTests(unittest.TestCase):
    def test_the_heartbeat_carries_the_daily_records_and_the_summary_merges_them_by_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            mid=store.create_meeting('Gün',{'model':'m'})
            store.add_segment(mid,Segment(0,10,'konuşma','system','K1',metrics={'cluster':'0:0','identity':{'name':'Ayşe'}},flags=FLAGS))
            store.status(mid,'complete')
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=reports.write_heartbeat(store,data,app={'version':'1.2.82','commit':'abc'})
                beat=json.loads(Path(path).read_text())
                self.assertEqual(len(beat['quality_daily']),1)
                self.assertEqual(beat['quality_daily'][0]['app_version'],'1.2.82')
                reports.write_heartbeat(store,data,app={'version':'1.2.82','commit':'abc'})   # again: same key, same day
                summary=reports.summarize(str(data/'shared'))
            records=summary['hosts']['Test-Mac']['heartbeat']['quality_daily']
            self.assertEqual(len(records),1)
            self.assertEqual(len(quality.daily_records(summary['hosts'])),1)
            self.assertIn('quality_trend',summary)
            store.close()


class TimelineReplayTests(unittest.TestCase):
    """Four meetings on four days: what the app would have said on the day, with nothing from the future."""

    def build(self,tmp):
        store=Store(Path(tmp)/'meeting-os.sqlite')
        def meeting(title,day,clusters):
            mid=store.create_meeting(title,{'model':'m'});t=0
            for speaker,vector in clusters:
                store.add_segment(mid,Segment(t,t+10,'konuşma','system',speaker,metrics={'cluster':f'0:{t//10}'},
                                              flags=FLAGS,embedding=vector,embedding_model='m'));t+=10
            store.status(mid,'complete')
            with store.db: store.db.execute('UPDATE meetings SET created=? WHERE id=?',(f'2026-01-0{day}T09:00:00+00:00',mid))
            return mid
        def date_samples(day):
            """Stamp everything enrolled so far with this day: a naming happens after its meeting, never before."""
            with store.db: store.db.execute("UPDATE samples SET created=? WHERE created IS NULL OR created>?",
                                            (f'2026-01-0{day}T18:00:00+00:00',f'2026-01-0{day}T18:00:00+00:00'))
        m1=meeting('M1',1,[('K1',[1.0,0.0,0.0]),('K2',[0.0,1.0,0.0])])
        store.enroll_speaker(m1,'K1','Ayşe');store.enroll_speaker(m1,'K2','Burak');date_samples(1)
        m2=meeting('M2',2,[('K1',[0.99,0.1,0.0]),('K2',[0.0,0.0,1.0])])
        store.enroll_speaker(m2,'K1','Ayşe');store.enroll_speaker(m2,'K2','Ceren');date_samples(2)
        m3=meeting('M3',3,[('K1',[0.0,0.05,0.998]),('K2',[0.6,0.8,0.0])])
        store.enroll_speaker(m3,'K1','Ceren');store.enroll_speaker(m3,'K2','Burak');date_samples(3)
        m4=meeting('M4',4,[('K1',[1.0,0.0,0.0]),('K2',[0.995,0.1,0.0])])
        store.enroll_speaker(m4,'K1','Deniz');store.enroll_speaker(m4,'K2','Burak');date_samples(4)
        return store,(m1,m2,m3,m4)

    def test_only_evidence_older_than_the_meeting_answers_and_an_unknown_voice_is_abstained(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,(m1,m2,m3,m4)=self.build(tmp)
            out=quality.replay_timeline(store)
            self.assertEqual(out['meetings'],4);self.assertEqual(out['clusters'],8)
            self.assertEqual(out['abstained_ok'],3)      # M1's two voices and Ceren in M2: nobody could have known them
            self.assertEqual(out['auto_correct'],2)      # Ayşe in M2, Ceren in M3
            self.assertEqual(out['abstained_wrong'],1)   # Burak in M3: known, and the evidence did not carry
            self.assertEqual(out['unknown_named'],1)     # Deniz in M4 named as somebody else
            self.assertEqual(out['auto_wrong'],1)        # Burak in M4 named as Ayşe
            self.assertEqual(out['auto_precision'],round(2/4,3))
            self.assertEqual(out['known_recall'],round(2/4,3))
            first=out['per_meeting'][0]
            self.assertEqual((first['meeting'],first['abstained_ok']),(m1,2))
            self.assertEqual([r['meeting'] for r in out['per_meeting']],[m1,m2,m3,m4])   # a timeline is in time order
            unknown=[i for i in out['items'] if i['outcome']=='unknown_named'][0]
            self.assertEqual((unknown['name'],unknown['named'],unknown['known_before']),('Deniz','Ayşe',False))
            store.close()

    def test_the_leave_one_out_replay_still_answers_and_is_the_more_generous_of_the_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,_=self.build(tmp)
            regression=quality.replay_identity(store)
            timeline=quality.replay_timeline(store)
            self.assertGreater(regression['ok'],timeline['auto_correct'])   # it may use samples from later meetings
            summary,full=quality.replay(store,tmp,timeline=True)
            self.assertIn('timeline',summary);self.assertIn('identity',summary)
            self.assertEqual(summary['timeline']['clusters'],8)
            self.assertEqual(json.loads(Path(summary['path']).read_text())['timeline']['meetings'],4)
            store.close()

    def test_a_sample_with_no_date_is_reported_rather_than_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,_=self.build(tmp)
            with store.db: store.db.execute('UPDATE samples SET created=NULL WHERE name=?',('Ayşe',))
            out=quality.replay_timeline(store)
            self.assertGreater(out['undated_samples'],0)
            self.assertEqual(out['auto_correct'],1)   # Ayşe can no longer be recognised from an undated sample
            store.close()

    def test_the_migration_dates_old_samples_from_the_meeting_they_came_from(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'meeting-os.sqlite';store=self.build(tmp)[0];store.close()
            import sqlite3
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE samples_old AS SELECT id,name,model,vector,duration,provenance,deleted_by FROM samples')
                db.execute('DROP TABLE samples')
                db.execute('ALTER TABLE samples_old RENAME TO samples')
            store=Store(path)
            dated=[r[0] for r in store.db.execute('SELECT created FROM samples')]
            self.assertTrue(all(d and d.startswith('2026-01-0') for d in dated),dated)
            self.assertEqual(Store.provenance_meeting('auto:abc123:0:1'),'abc123')
            self.assertEqual(Store.provenance_meeting('abc123:speaker:K1'),'abc123')
            self.assertIsNone(Store.provenance_meeting('manual'));self.assertIsNone(Store.provenance_meeting('team:mac:9f'))
            store.close()


class FixtureGeneratorTests(unittest.TestCase):
    """The real-size fixtures and the generator that builds them — no network, no model, no money."""
    NEW=('long_multi_chunk','real_size_chunk','late_reversal','topic_coverage','owner_handover_long','due_shift_long')

    def test_the_six_cases_exist_in_the_case_shape_the_gates_read(self):
        from meeting_os.evaluation import check_fixture_analysis,fixture_rows
        for name in self.NEW:
            with self.subTest(case=name):
                case=json.loads((FIXTURES/f'{name}.json').read_text(encoding='utf-8'))
                self.assertEqual(len(case['expected_action_fields']),case['expected_actions'])
                self.assertEqual(len(case['expected_owners']),case['expected_actions'])
                self.assertTrue(case['note'].startswith('Tamamen kurgudur'))
                rows=fixture_rows(case)
                self.assertEqual([r['id'] for r in rows],list(range(1,len(case['segments'])+1)))
                # The gate runs against an empty answer without raising: a missing task is a FAIL, not a crash.
                checks=check_fixture_analysis({'actions':[]},case)
                self.assertFalse(checks['action_count'])

    def test_every_expected_term_is_really_in_the_transcript(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        import importlib.util
        spec=importlib.util.spec_from_file_location('make_fixture',ROOT/'scripts/make-fixture.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in self.NEW:
            with self.subTest(case=name):
                case=json.loads((FIXTURES/f'{name}.json').read_text(encoding='utf-8'))
                self.assertEqual(module.validate(name,case,module.SPECS[name]),[])

    def test_the_long_cases_are_real_chunk_size_and_split_the_way_the_spec_says(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('make_fixture',ROOT/'scripts/make-fixture.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        measured={}
        for name in self.NEW:
            case=json.loads((FIXTURES/f'{name}.json').read_text(encoding='utf-8'))
            measured[name]=(module._tokens(case['segments']),module.chunk_count(case))
        self.assertEqual(measured['long_multi_chunk'][1],3)
        self.assertEqual(measured['real_size_chunk'][1],1)
        for name,(tokens,chunks) in measured.items():
            self.assertGreater(tokens,6000,name)                 # a real chunk, not the ≈2k the old set had
            self.assertGreater(tokens/chunks,5000,name)          # every chunk is genuinely full

    def test_the_generator_is_deterministic_and_the_files_match_it(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/make-fixture.py'),'--check'],capture_output=True,text=True,cwd=str(ROOT))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for name in self.NEW: self.assertIn(name,result.stdout)

    def test_a_reversal_planted_late_really_is_in_the_last_chunk(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('make_fixture',ROOT/'scripts/make-fixture.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        from meeting_os.evaluation import fixture_rows
        from meeting_os.intelligence import CHUNK_BUDGET,chunks
        case=json.loads((FIXTURES/'late_reversal.json').read_text(encoding='utf-8'))
        batches=list(chunks(fixture_rows(case),module._Counter(),budget=CHUNK_BUDGET))
        last=' '.join(item['text'] for item in batches[-1])
        self.assertIn('iptal ediyoruz',last)
        self.assertNotIn('iptal ediyoruz',' '.join(item['text'] for item in batches[0]))

    def test_the_cloud_benchmark_reports_seconds_topics_and_the_model_that_answered(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('bench',ROOT/'scripts/benchmark-analysis-cloud.py')
        bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
        timing=bench.seconds_report([{'case':'a','elapsed_seconds':4.0},{'case':'a','elapsed_seconds':8.0},{'case':'b','elapsed_seconds':100.0}])
        self.assertEqual((timing['p50'],timing['max'],timing['cases']),(8.0,100.0,3))
        self.assertEqual(timing['per_case']['a']['runs'],2)
        case=json.loads((FIXTURES/'topic_coverage.json').read_text(encoding='utf-8'))
        covered=[{'text':' '.join(g[0] for g in case['expected_topic_terms'])}]
        self.assertEqual(bench.missing_topics({'summary':covered},case),[])
        missing=bench.missing_topics({'summary':[{'text':'yalnız kavak konuşuldu'}],
                                      'section_summaries':[{'text':' '.join(g[0] for g in case['expected_topic_terms'])}]},case)
        self.assertEqual(len(missing),len(case['expected_topic_terms'])-1)
        self.assertTrue(all(m['lost_in_compaction'] for m in missing))   # the chunks had it; the compaction lost it
        self.assertEqual(bench.missing_topics({'summary':[]},{'segments':[]}),[])


if __name__=='__main__': unittest.main()
