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

class FixtureGateTests(unittest.TestCase):
 def case(self):
  return {'expected_actions':2,'expected_owners':['Boran','Ece'],'forbidden_action_terms':[],
   'expected_action_fields':[{'title_terms':['PRD'],'owner':'Boran','due_text':'yarın'},
                            {'title_terms':['kabul','kriter'],'owner':'Ece','due_text':'cuma gününe kadar'}]}
 def test_owner_set_cannot_hide_swapped_task_ownership(self):
  from meeting_os.evaluation import check_fixture_analysis
  r=check_fixture_analysis({'actions':[{'title':'PRD hazırla','owner':'Ece','due_text':'cuma gününe kadar'},
   {'title':'kabul kriterlerini yaz','owner':'Boran','due_text':'yarın'}]},self.case())
  self.assertTrue(r['owner_set']);self.assertFalse(r['task_owner_due_pairs'])
 def test_wrong_date_fails_even_when_count_owner_title_match(self):
  from meeting_os.evaluation import check_fixture_analysis
  r=check_fixture_analysis({'actions':[{'title':'PRD hazırla','owner':'Boran','due_text':'gelecek hafta'},
   {'title':'kabul kriterlerini yaz','owner':'Ece','due_text':'cuma gününe kadar'}]},self.case())
  self.assertFalse(r['task_owner_due_pairs'])
 def test_correct_pairs_pass_regardless_of_order(self):
  from meeting_os.evaluation import check_fixture_analysis
  r=check_fixture_analysis({'actions':[{'title':'kabul kriterlerini yaz','owner':'Ece','due_text':'cuma gününe kadar'},
   {'title':'PRD hazırla','owner':'Boran','due_text':'yarın'}]},self.case())
  self.assertTrue(all(r.values()))
