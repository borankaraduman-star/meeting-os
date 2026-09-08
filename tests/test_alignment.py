import unittest
from meeting_os.pipeline import split_by_speaker
class AlignmentTests(unittest.TestCase):
    def test_word_splits_at_speaker_change(self):
        row={'start':0,'end':4,'text':'Merhaba İpek şimdi ben','words':[{'start':0,'end':1,'word':'Merhaba'},{'start':1,'end':2,'word':' İpek'},{'start':2,'end':3,'word':' şimdi'},{'start':3,'end':4,'word':' ben'}]}
        parts=split_by_speaker(row,0,[(0,2,'a'),(2,4,'b')])
        self.assertEqual([p['text'] for p in parts],['Merhaba İpek','şimdi ben'])
        self.assertEqual([(p['start'],p['end']) for p in parts],[(0,2),(2,4)])
    def test_no_words_preserves_text(self):
        row={'start':0,'end':4,'text':'Original text'}
        self.assertEqual(split_by_speaker(row,0,[]),[row])
