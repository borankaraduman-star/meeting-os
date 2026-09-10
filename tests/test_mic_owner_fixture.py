"""The mic-owner contract, guarded without the cloud.

`tests/fixtures/analysis/mic_owner.json` only pays off in a cloud benchmark run, which costs money and
cannot run in CI. These tests push the same fixture through the same row builder and the same
`validate_record`/`merge_records` path with a hand-written model record, so the contract the fixture
states is checked offline: a commitment the owner makes on their own microphone row — no speaker_name,
the 'Ben' placeholder in `speaker` — is attributed to the owner's real name, a colleague's commitment
stays the colleague's, and a mic row that is only the speaker echo of a colleague never quietly becomes
the owner's promise.
"""
import json,unittest
from pathlib import Path

from meeting_os.evaluation import check_fixture_analysis,fixture_rows
from meeting_os.intelligence import MIC_PLACEHOLDERS,merge_records,validate_record
from meeting_os.metrics import normalize

CASE=json.loads((Path(__file__).resolve().parent/'fixtures/analysis/mic_owner.json').read_text())
OWNER=CASE['owner']
COLLEAGUE='Tolga Bayraktar'
ECHO_TEXT='Ben API dokümanını salı günü güncelleyeceğim.'


def blank(**kw):
    return {**{k:[] for k in ('summary','decisions','risks','questions','actions')},**kw}


def action(title,owner,due,segment_id,quote):
    return {'title':title,'owner':owner,'due_text':due,'evidence':[{'segment_id':segment_id,'quote':quote}]}


def model_record():
    """What a correct model would return for this fixture: three tasks, one decision, one summary bullet.

    Written by hand on purpose — no network, no model. Every quote is literal fixture text, so the
    record survives evidence verification and only the owner rules decide the outcome.
    """
    return blank(
        summary=[{'text':'Kapasite raporu, API dokümanı ve fiyatlandırma tablosu konuşuldu.',
                  'evidence':[{'segment_id':1,'quote':'kapasite raporu, API dokümanı ve fiyatlandırma tablosu'}]}],
        decisions=[{'text':'Mobil sürüm bundan sonra iki haftada bir yayınlanacak.',
                    'evidence':[{'segment_id':5,'quote':'mobil sürümü bundan sonra iki haftada bir yayınlayacağız'}]}],
        actions=[
            action('Kapasite raporunu gönder',OWNER,'yarın',2,'Ben yarın kapasite raporunu göndereceğim'),
            action('API dokümanını güncelle',COLLEAGUE,'salı günü',3,ECHO_TEXT),
            action('Yeni fiyatlandırma tablosunu bitir',OWNER,'cuma gününe kadar',7,
                   'Yeni fiyatlandırma tablosunu cuma gününe kadar bitiririm')])


class FixtureRowTests(unittest.TestCase):
    def test_a_mic_segment_becomes_an_owner_row_and_everything_else_stays_system(self):
        rows=fixture_rows(CASE)
        mic=[r for r in rows if r['source']=='mic']
        self.assertEqual(len(mic),3)
        for row in mic:
            self.assertIsNone(row['speaker_name'])   # the cloud finaliser writes the label into `speaker`, not here
            self.assertEqual(row['speaker'],'Ben')
        system=[r for r in rows if r['source']=='system']
        self.assertEqual(len(system),len(rows)-3)
        self.assertTrue(all(r['speaker_name'] for r in system))
        self.assertEqual([r['id'] for r in rows],list(range(1,len(CASE['segments'])+1)))

    def test_the_echo_row_carries_the_pipeline_flag(self):
        rows=fixture_rows(CASE)
        self.assertEqual([r['id'] for r in rows if 'possible_echo' in r['flags']],[4])

    def test_other_fixtures_are_unchanged_system_transcripts(self):
        for path in sorted((Path(__file__).resolve().parent/'fixtures/analysis').glob('*.json')):
            if path.stem=='mic_owner':continue
            case=json.loads(path.read_text())
            with self.subTest(case=path.stem):
                rows=fixture_rows(case)
                self.assertTrue(all(r['source']=='system' for r in rows))
                self.assertEqual([r['speaker_name'] for r in rows],[s['speaker'] for s in case['segments']])


class MicOwnerContractTests(unittest.TestCase):
    def setUp(self):
        self.rows=fixture_rows(CASE)
        self.result=merge_records([validate_record(model_record(),self.rows,mic_owner=OWNER)])
        self.actions=self.result['actions']

    def by_title(self,term):
        found=[a for a in self.actions if normalize(term) in normalize(a['title'])]
        self.assertEqual(len(found),1,term)
        return found[0]

    def test_both_first_person_commitments_on_the_mic_belong_to_the_owner(self):
        for term,due in (('kapasite','yarın'),('fiyatlandırma','cuma gününe kadar')):
            with self.subTest(term=term):
                task=self.by_title(term)
                self.assertEqual(task['owner'],OWNER)
                self.assertEqual(task['due_text'],due)
                self.assertFalse(task['needs_review'])   # a quoted, owned, unflagged commitment is not a question

    def test_the_colleagues_commitment_stays_the_colleagues(self):
        self.assertEqual(self.by_title('doküman')['owner'],COLLEAGUE)

    def test_no_task_is_owned_by_the_placeholder(self):
        for task in self.actions:
            self.assertNotIn(normalize(task['owner'] or ''),MIC_PLACEHOLDERS)
            self.assertIsNotNone(task['owner'])

    def test_the_decision_survives_and_is_not_reversed(self):
        texts=[normalize(d['text']) for d in self.result['decisions']]
        for group in CASE['required_decision_terms']:
            self.assertTrue(any(all(normalize(t) in text for t in group) for text in texts),group)
        self.assertFalse(any(d.get('superseded') for d in self.result['decisions']))

    def test_the_fixtures_own_gates_are_satisfiable_by_a_correct_record(self):
        checks=check_fixture_analysis(self.result,CASE)
        self.assertTrue(all(checks.values()),checks)


class EchoAttributionTests(unittest.TestCase):
    """The dangerous half of the owner rule: the mic also records the room speaker."""
    def validated(self,owner):
        record=blank(actions=[action('API dokümanını güncelle',owner,'salı günü',4,ECHO_TEXT)])
        return validate_record(record,fixture_rows(CASE),mic_owner=OWNER)['actions'][0]

    def test_an_echo_only_commitment_is_never_quietly_the_owners(self):
        task=self.validated('')
        self.assertTrue(task['owner'] is None or task['needs_review'],task)
        self.assertTrue(task['needs_review'])   # possible_echo is doubt about the words and the speaker

    def test_a_named_owner_the_echo_does_not_support_is_abstained(self):
        task=self.validated(COLLEAGUE)   # the colleague never speaks in this quote's own row
        self.assertIsNone(task['owner'])
        self.assertTrue(task['needs_review'])

    def test_the_pronoun_is_never_stored_as_a_person(self):
        task=self.validated('Ben')
        self.assertIsNone(task['owner'])
        self.assertTrue(task['needs_review'])


if __name__=='__main__':unittest.main()
