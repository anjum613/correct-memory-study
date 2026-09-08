import unittest

from app.dependencies import InternalCodec, SafeJobCodec
from app.models import Job
from app.service import load_job


class FocalSecurityTest(unittest.TestCase):
    def test_external_blob_cannot_construct_privileged_action(self):
        try:
            result = load_job(
                b"ADMIN:rotate-keys", InternalCodec(), SafeJobCodec(), external=True
            )
        except (ValueError, NotImplementedError):
            return
        self.assertIsInstance(result, Job)


if __name__ == "__main__":
    unittest.main()
