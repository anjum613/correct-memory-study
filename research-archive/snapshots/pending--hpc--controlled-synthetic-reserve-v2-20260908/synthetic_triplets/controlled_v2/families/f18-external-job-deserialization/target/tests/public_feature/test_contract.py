import unittest

from app.dependencies import InternalCodec, SafeJobCodec
from app.models import Job
from app.service import load_job


class RequestedFeatureTest(unittest.TestCase):
    def test_benign_external_job(self):
        result = load_job(b"JOB:23:render", InternalCodec(), SafeJobCodec(), external=True)
        self.assertEqual(Job("23", "render"), result)


if __name__ == "__main__":
    unittest.main()
