import unittest

from app.dependencies import ChildStore
from app.models import Child, Parent
from app.service import get_child


class ExistingBehaviourTest(unittest.TestCase):
    def test_first_child_default(self):
        child = Child("c1", "p1", "note")
        self.assertEqual(child, get_child(Parent("p1", ("c1",)), ChildStore([child])))


if __name__ == "__main__":
    unittest.main()
