from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    job_id: str
    action: str


@dataclass(frozen=True)
class PrivilegedAction:
    action: str
