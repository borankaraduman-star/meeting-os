import unittest
from meeting_os.evaluation import score_analysis
class EvaluationTests(unittest.TestCase):
 def test_false_positive_and_owner_error_are_visible(self):
  result=score_analysis({'actions':[{'owner':'Ece','due_text':'yarın'},{'owner':None}],'summary':[{'text':'x'}]},{'actions':[{'id':'a','owner':'Boran','due_text':'yarın'}],'matches':[{'predicted':0,'reference':'a'}],'unsupported_summary_indices':[0]})
  self.assertEqual(result['action_precision'],.5);self.assertEqual(result['action_recall'],1);self.assertEqual(result['owner_accuracy_on_matched'],0);self.assertEqual(result['unsupported_summary_fraction'],1)
 def test_duplicate_match_rejected(self):
  with self.assertRaises(ValueError):score_analysis({'actions':[{}]},{'actions':[{'id':'a'}],'matches':[{'predicted':0,'reference':'a'}]*2})
 def test_empty_denominators_not_perfect(self):
  r=score_analysis({'actions':[]},{'actions':[],'matches':[]});self.assertIsNone(r['action_f1']);self.assertIsNone(r['action_precision'])
