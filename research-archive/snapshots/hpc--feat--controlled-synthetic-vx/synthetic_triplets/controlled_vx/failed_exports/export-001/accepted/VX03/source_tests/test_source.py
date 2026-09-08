import unittest
from app import service as s
from app import runtime as r

class Source(unittest.TestCase):
    def test_generated_exports(self):
        store = r.VirtualStore()
        got = s.export_generated([dict(id=-4, title='Daily', body='ready')], store, format_name='upper')
        self.assertEqual({'/exports/report--4.txt': 'DAILY\nREADY'}, store.entries)
        self.assertEqual(dict(paths=['report--4.txt'], characters=[11], total=11, count=1), got)

if __name__ == '__main__':
    unittest.main(verbosity=2)
