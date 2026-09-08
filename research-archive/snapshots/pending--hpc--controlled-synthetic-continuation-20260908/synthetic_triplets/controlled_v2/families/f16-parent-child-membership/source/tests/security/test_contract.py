import unittest

from app.dependencies import ChildStore
from app.models import Child, Parent
from app.service import get_selected_child


class SourceSecurityTest(unittest.TestCase):
    def test_parent_list_cannot_select_unrelated_child(self):
        own = Child("c1", "p1", "note")
        foreign = Child("c2", "p2", "private")
        parent = Parent("p1", ("c1",))
        store = ChildStore([own, foreign])
        self.assertEqual("p1", get_selected_child(parent, 0, store).parent_id)
        with self.assertRaises(IndexError):
            get_selected_child(parent, 1, store)


if __name__ == "__main__":
    unittest.main()
