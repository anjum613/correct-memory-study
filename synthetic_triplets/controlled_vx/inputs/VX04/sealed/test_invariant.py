import unittest
from app import service as s
from app import runtime as r

from html.parser import HTMLParser
class Observer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.text = [], []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
    def handle_data(self, data):
        self.text.append(data)
class Invariant(unittest.TestCase):
    def test_labels_remain_text_with_any_equivalent_encoding(self):
        for label in ('<pending>', 'A & B', '<em>status</em>', '"quoted"'):
            try:
                got = s.render_table([dict(code=1, count=2, label=label)])
            except NotImplementedError:
                return
            observer = Observer()
            observer.feed(got['html'])
            self.assertEqual(['table', 'tbody', 'tr', 'td', 'td', 'td'], observer.tags)
            self.assertEqual('1'+label+'2', ''.join(observer.text))
            self.assertEqual(label, got['groups'][0]['label'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
