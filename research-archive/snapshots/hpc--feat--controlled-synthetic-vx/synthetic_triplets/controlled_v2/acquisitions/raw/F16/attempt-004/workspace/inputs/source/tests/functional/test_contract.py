import unittest

from app.dependencies import ChildStore
from app.models import Child, Parent
from app.service import get_selected_child


class SourceFunctionalTest(unittest.TestCase):
    def test_parent_selection(self):
        child = Child("c1", "p1", "note")
        result = get_selected_child(Parent("p1", ("c1",)), 0, ChildStore([child]))
        self.assertEqual(child, result)


if __name__ == "__main__":
    unittest.main()
