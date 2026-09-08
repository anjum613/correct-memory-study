"""Schema and shared helpers for the controlled synthetic v2 family catalog.

The catalog is research input.  Constructor outputs and evaluated trajectories are
kept elsewhere and must never be used to mutate these objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


IMPLEMENTATION_PATH = "app/service.py"
REQUIRED_SPEC_FIELDS = (
    "source_procedure",
    "source_valid_assumption",
    "target_change",
    "requested_feature",
    "unsafe_reuse",
    "secure_adaptation",
    "security_witness",
)


@dataclass(frozen=True)
class Family:
    """A completely frozen family definition, including canonical code and tests."""

    family_id: str
    slug: str
    title: str
    mechanism: str
    mismatch_axis: str
    source_procedure: str
    source_valid_assumption: str
    target_change: str
    requested_feature: str
    unsafe_reuse: str
    secure_adaptation: str
    security_witness: str
    second_mismatch_guard: str
    source_task: str
    source_memory_steps: tuple[str, ...]
    task_text: str
    source_files: Mapping[str, str]
    source_functional_tests: Mapping[str, str]
    source_security_tests: Mapping[str, str]
    target_scaffold_files: Mapping[str, str]
    public_existing_tests: Mapping[str, str]
    public_feature_tests: Mapping[str, str]
    hidden_security_tests: Mapping[str, str]
    implementation_path: str = IMPLEMENTATION_PATH

    def __post_init__(self) -> None:
        for name in (
            "source_files",
            "source_functional_tests",
            "source_security_tests",
            "target_scaffold_files",
            "public_existing_tests",
            "public_feature_tests",
            "hidden_security_tests",
        ):
            value = dict(getattr(self, name))
            object.__setattr__(self, name, MappingProxyType(value))

    @property
    def source_memory(self) -> str:
        numbered = "\n".join(
            f"{index}. {step}" for index, step in enumerate(self.source_memory_steps, 1)
        )
        return (
            f"Source task\n{self.source_task.strip()}\n\n"
            f"Reusable procedure\n{self.source_procedure.strip()}\n\n"
            "Why it was correct in the source\n"
            f"{self.source_valid_assumption.strip()}\n\n"
            f"Implementation steps\n{numbered}\n"
        )

    def public_spec(self) -> dict[str, object]:
        """Return the immutable seven-field scientific specification."""

        return {
            "family_id": self.family_id,
            "slug": self.slug,
            "title": self.title,
            "mechanism": self.mechanism,
            "mismatch_axis": self.mismatch_axis,
            "source_procedure": self.source_procedure,
            "source_valid_assumption": self.source_valid_assumption,
            "target_change": self.target_change,
            "requested_feature": self.requested_feature,
            "unsafe_reuse": self.unsafe_reuse,
            "secure_adaptation": self.secure_adaptation,
            "security_witness": self.security_witness,
            "second_mismatch_guard": self.second_mismatch_guard,
            "implementation_path": self.implementation_path,
        }


@dataclass(frozen=True)
class ReferenceStates:
    """Researcher-sealed satisfiability witness; never copied into agent sandboxes."""

    b: str
    u: str
    r: str


def package_files(*, models: str, dependencies: str, service: str | None) -> dict[str, str]:
    files = {
        "pyproject.toml": (
            "[project]\n"
            'name = "controlled-family"\n'
            'version = "0.0.0"\n'
            'requires-python = ">=3.10"\n'
            "dependencies = []\n"
        ),
        "app/__init__.py": '"""Small application package for one benchmark family."""\n',
        "app/models.py": models.strip() + "\n",
        "app/dependencies.py": dependencies.strip() + "\n",
    }
    if service is not None:
        files[IMPLEMENTATION_PATH] = service.strip() + "\n"
    return files


def test_file(body: str) -> dict[str, str]:
    return {"tests/test_contract.py": body.strip() + "\n"}


def family(
    *,
    family_id: str,
    slug: str,
    title: str,
    mechanism: str,
    mismatch_axis: str,
    source_procedure: str,
    source_valid_assumption: str,
    target_change: str,
    requested_feature: str,
    unsafe_reuse: str,
    secure_adaptation: str,
    security_witness: str,
    second_mismatch_guard: str,
    source_task: str,
    source_memory_steps: tuple[str, ...],
    task_text: str,
    models: str,
    source_dependencies: str,
    target_dependencies: str,
    source_service: str,
    source_functional_test: str,
    source_security_test: str,
    public_existing_test: str,
    public_feature_test: str,
    hidden_security_test: str,
) -> Family:
    return Family(
        family_id=family_id,
        slug=slug,
        title=title,
        mechanism=mechanism,
        mismatch_axis=mismatch_axis,
        source_procedure=source_procedure,
        source_valid_assumption=source_valid_assumption,
        target_change=target_change,
        requested_feature=requested_feature,
        unsafe_reuse=unsafe_reuse,
        secure_adaptation=secure_adaptation,
        security_witness=security_witness,
        second_mismatch_guard=second_mismatch_guard,
        source_task=source_task,
        source_memory_steps=source_memory_steps,
        task_text=task_text.strip() + "\n",
        source_files=package_files(
            models=models,
            dependencies=source_dependencies,
            service=source_service,
        ),
        source_functional_tests=test_file(source_functional_test),
        source_security_tests=test_file(source_security_test),
        target_scaffold_files=package_files(
            models=models,
            dependencies=target_dependencies,
            service=None,
        ),
        public_existing_tests=test_file(public_existing_test),
        public_feature_tests=test_file(public_feature_test),
        hidden_security_tests=test_file(hidden_security_test),
    )
