import unittest
from app import service as s
from app import runtime as r

class Feature(unittest.TestCase):
    def test_formats_and_order(self):
        rows = [dict(id=1, title='A', body='one', name='team/a.txt'), dict(id=2, title='B', body='two')]
        for fmt in ('text', 'upper'):
            store = r.VirtualStore()
            got = s.export_batch(rows, store, format_name=fmt)
            self.assertEqual(dict(paths=['team/a.txt', 'report-2.txt'], characters=[5, 5], total=10, count=2), got)
            self.assertEqual('A\nONE' if fmt == 'upper' else 'A\none', store.entries['/exports/team/a.txt'])
            self.assertEqual(1, store.commits)
    def test_empty(self):
        store = r.VirtualStore()
        self.assertEqual(dict(paths=[], characters=[], total=0, count=0), s.export_batch([], store))
        self.assertEqual(1, store.commits)
    def test_rejections_are_atomic(self):
        good = dict(id=1, title='A', body='one', name='team/a.txt')
        for bad in (dict(id=2, title='B', body='two', name='team/./a.txt'),
                    dict(id='bad', title='B', body='two'), dict(id=2, title=7, body='two')):
            store = r.VirtualStore()
            with self.assertRaises(ValueError):
                s.export_batch([good, bad], store)
            self.assertEqual({}, store.entries)
            self.assertEqual(0, store.commits)
        with self.assertRaises(ValueError):
            s.export_batch([], r.VirtualStore(), format_name='unknown')

if __name__ == '__main__':
    unittest.main(verbosity=2)
