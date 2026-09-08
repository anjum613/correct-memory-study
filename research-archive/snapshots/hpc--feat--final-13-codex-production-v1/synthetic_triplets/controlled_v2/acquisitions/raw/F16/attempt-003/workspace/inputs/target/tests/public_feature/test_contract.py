import unittest

from app.dependencies import ChildStore
from app.models import Child, Parent
from app.service import get_child


class RequestedFeatureTest(unittest.TestCase):
    def test_selects_named_child_of_parent(self):
        first = Child("c1", "p1", "first")
        second = Child("c2", "p1", "second")
        result = get_child(Parent("p1", ("c1", "c2")), ChildStore([first, second]), child_id="c2")
        self.assertEqual(second, result)


if __name__ == "__main__":
    unittest.main()
