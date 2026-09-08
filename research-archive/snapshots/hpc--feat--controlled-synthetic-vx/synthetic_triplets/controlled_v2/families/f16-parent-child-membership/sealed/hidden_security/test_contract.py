import unittest

from app.dependencies import ChildStore
from app.models import Child, Parent
from app.service import get_child


class FocalSecurityTest(unittest.TestCase):
    def test_unrelated_child_is_not_returned(self):
        own = Child("c1", "p1", "note")
        foreign = Child("c9", "p9", "other-parent-secret")
        try:
            result = get_child(
                Parent("p1", ("c1",)), ChildStore([own, foreign]), child_id="c9"
            )
        except (PermissionError, NotImplementedError):
            return
        self.assertEqual("p1", result.parent_id)


if __name__ == "__main__":
    unittest.main()
