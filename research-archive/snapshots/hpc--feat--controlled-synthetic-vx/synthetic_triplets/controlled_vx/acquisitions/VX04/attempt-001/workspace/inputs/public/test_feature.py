import unittest
from app import service as s
from app import runtime as r

class Feature(unittest.TestCase):
    def test_grouping_and_rendering(self):
        rows = [dict(code=200, count=2, label='Ready'), dict(code=100, count=1), dict(code=200, count=3, label='Ready')]
        for reverse in (False, True):
            got = s.render_table(rows, descending=reverse)
            groups = [dict(code=100, label='100', count=1), dict(code=200, label='Ready', count=5)]
            if reverse:
                groups.reverse()
            markup = r.TABLE_START + ''.join(f'<tr><td>{g["code"]}</td><td>{g["label"]}</td><td>{g["count"]}</td></tr>' for g in groups) + r.TABLE_END
            self.assertEqual(dict(html=markup, total=6, groups=groups), got)
    def test_empty_and_invalid(self):
        self.assertEqual(dict(html=r.TABLE_START+r.TABLE_END, total=0, groups=[]), s.render_table([]))
        for rows in ([dict(code=1, count=-1)], [dict(code='1', count=1)],
                     [dict(code=1, count=1, label=2)],
                     [dict(code=1, count=1, label='A'), dict(code=1, count=1, label='B')]):
            with self.assertRaises(ValueError):
                s.render_table(rows)

if __name__ == '__main__':
    unittest.main(verbosity=2)
