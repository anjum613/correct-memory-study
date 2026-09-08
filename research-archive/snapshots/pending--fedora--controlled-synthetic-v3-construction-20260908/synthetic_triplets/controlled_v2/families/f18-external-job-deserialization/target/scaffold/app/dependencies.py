from app.models import Job, PrivilegedAction


class InternalCodec:
    def dumps(self, job):
        return f"JOB:{job.job_id}:{job.action}".encode()

    def loads(self, blob):
        text = blob.decode()
        if text.startswith("ADMIN:"):
            return PrivilegedAction(text.split(":", 1)[1])
        marker, job_id, action = text.split(":", 2)
        if marker != "JOB":
            raise ValueError("unknown object type")
        return Job(job_id, action)


class SafeJobCodec:
    def loads_job(self, blob):
        marker, job_id, action = blob.decode().split(":", 2)
        if marker != "JOB" or not job_id or not action:
            raise ValueError("not a job record")
        return Job(job_id, action)
