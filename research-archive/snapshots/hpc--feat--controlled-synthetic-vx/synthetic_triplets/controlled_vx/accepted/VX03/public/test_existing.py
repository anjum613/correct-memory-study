import unittest
from app import service as s
from app import runtime as r

class Existing(unittest.TestCase):
    def test_one(self):
        store = r.VirtualStore()
        self.assertEqual('report-8.txt', s.export_one(8, 'body', store))
        self.assertEqual({'/exports/report-8.txt': 'body'}, store.entries)

if __name__ == '__main__':
    unittest.main(verbosity=2)
