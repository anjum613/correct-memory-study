import unittest

from app.dependencies import InternalCodec
from app.models import Job
from app.service import load_queued_job


class SourceFunctionalTest(unittest.TestCase):
    def test_queue_round_trip(self):
        codec = InternalCodec()
        job = Job("17", "build")
        self.assertEqual(job, load_queued_job(codec.dumps(job), codec))


if __name__ == "__main__":
    unittest.main()
