import unittest

from app.dependencies import InternalCodec
from app.models import Job
from app.service import load_queued_job


class SourceSecurityTest(unittest.TestCase):
    def test_server_serializer_produces_only_job_marker(self):
        codec = InternalCodec()
        blob = codec.dumps(Job("17", "build"))
        self.assertTrue(blob.startswith(b"JOB:"))
        self.assertIsInstance(load_queued_job(blob, codec), Job)


if __name__ == "__main__":
    unittest.main()
