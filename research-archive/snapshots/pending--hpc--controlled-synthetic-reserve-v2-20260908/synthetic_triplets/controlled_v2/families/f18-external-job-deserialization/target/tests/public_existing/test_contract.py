import unittest

from app.dependencies import InternalCodec, SafeJobCodec
from app.models import Job
from app.service import load_job


class ExistingBehaviourTest(unittest.TestCase):
    def test_internal_queue_job(self):
        codec = InternalCodec()
        job = Job("17", "build")
        self.assertEqual(job, load_job(codec.dumps(job), codec, SafeJobCodec()))


if __name__ == "__main__":
    unittest.main()
