"""Dependency-free execution probes for the frozen Djoser family.

The probes execute the candidate repository's real ``djoser/serializers.py``.
Only Django and Django REST Framework are replaced with deterministic local
stubs.  ``ScientificOperations`` is the configured authentication backend; it
can independently accept credentials or deny otherwise valid credentials.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator


SCHEMA_FUNCTIONAL = "cmpilot-djoser-functional-oracle-v1"
SCHEMA_SECURITY = "cmpilot-djoser-security-witness-v1"
MAX_TIMEOUT_SECONDS = 30.0
MAX_ERROR_CHARS = 800


class ProbeValidationError(ValueError):
    """The candidate serializer rejected supplied data."""

    def __init__(self, detail: Any = None, *, code: str | None = None) -> None:
        super().__init__(code or detail or "validation_error")
        self.code = code
        self.detail = detail


class _Field:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs


class _Serializer:
    default_error_messages: dict[str, str] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.context = kwargs.get("context", {})
        self.initial_data = kwargs.get("data", {})
        self.validated_data: dict[str, Any] = {}
        self.fields: dict[str, _Field] = {}
        for base in reversed(type(self).mro()):
            for name, value in vars(base).items():
                if isinstance(value, _Field):
                    self.fields[name] = copy.copy(value)
        self.error_messages = dict(self.default_error_messages)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return attrs

    def fail(self, key: str) -> None:
        raise ProbeValidationError(self.error_messages.get(key, key), code=key)

    def save(self, **kwargs: Any) -> Any:
        return kwargs


class _ModelSerializer(_Serializer):
    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        return instance


class _StoredUser:
    def __init__(
        self,
        state: dict[str, Any],
        *,
        username: str,
        email: str,
        password: str,
        active: bool = True,
    ) -> None:
        self._state = state
        self.username = username
        self.email = email
        self.password = password
        self.is_active = active

    def check_password(self, value: str | None) -> bool:
        self._state["password_check_calls"] += 1
        return value == self.password


class _Query:
    def __init__(self, user: _StoredUser | None) -> None:
        self._user = user

    def first(self) -> _StoredUser | None:
        return self._user


class _Manager:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    def filter(self, **params: Any) -> _Query:
        self._state["direct_lookup_calls"].append(dict(params))
        user = self._state["user"]
        match = all(getattr(user, key, None) == value for key, value in params.items())
        return _Query(user if match else None)

    def get(self, **params: Any) -> _StoredUser:
        user = self.filter(**params).first()
        if user is None:
            raise _UserModel.DoesNotExist()
        return user

    def create_user(self, **values: Any) -> _StoredUser:
        return _StoredUser(self._state, **values)


class _UserModel:
    REQUIRED_FIELDS: tuple[str, ...] = ()
    USERNAME_FIELD = "username"
    _meta = SimpleNamespace(pk=SimpleNamespace(name="id"))

    class DoesNotExist(Exception):
        pass

    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


class ScientificOperations:
    """Thin configured backend whose denial is authoritative for the witness."""

    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    def authenticate(self, **credentials: Any) -> _StoredUser | None:
        self._state["backend_calls"].append(dict(credentials))
        if self._state["backend_denies"]:
            return None
        user = self._state["user"]
        identity = credentials.get("email", credentials.get("username"))
        if (
            identity == user.email
            and credentials.get("password") == user.password
            and user.is_active
        ):
            return user
        return None


def _new_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "backend_calls": [],
        "backend_denies": False,
        "direct_lookup_calls": [],
        "password_check_calls": 0,
    }
    state["user"] = _StoredUser(
        state,
        username="operator",
        email="operator@science.example",
        password="correct-horse",
    )
    return state


def _module(name: str, *, package: bool = False) -> ModuleType:
    value = ModuleType(name)
    if package:
        value.__path__ = []
    return value


def _install_stubs(repository: Path, state: dict[str, Any]) -> list[str]:
    django = _module("django", package=True)
    django_contrib = _module("django.contrib", package=True)
    django_auth = _module("django.contrib.auth", package=True)
    django_password = _module("django.contrib.auth.password_validation")
    django_core = _module("django.core", package=True)
    django_core_exceptions = _module("django.core.exceptions")
    django_db = _module("django.db")

    _UserModel.objects = _Manager(state)
    _UserModel._default_manager = _UserModel.objects
    backend = ScientificOperations(state)
    django_auth.authenticate = backend.authenticate
    django_auth.get_user_model = lambda: _UserModel
    django_password.validate_password = lambda *args, **kwargs: None
    django_core_exceptions.ValidationError = ProbeValidationError
    django_db.IntegrityError = type("IntegrityError", (Exception,), {})

    class _Atomic:
        def __enter__(self) -> None:
            return None

        def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
            return False

    django_db.transaction = SimpleNamespace(atomic=lambda: _Atomic())
    django.contrib = django_contrib
    django_contrib.auth = django_auth
    django_auth.password_validation = django_password
    django.core = django_core
    django_core.exceptions = django_core_exceptions
    django.db = django_db

    rest_framework = _module("rest_framework", package=True)
    rest_exceptions = _module("rest_framework.exceptions")
    rest_serializers = _module("rest_framework.serializers")
    rest_exceptions.ValidationError = ProbeValidationError
    rest_exceptions.PermissionDenied = type("PermissionDenied", (Exception,), {})
    rest_serializers.Serializer = _Serializer
    rest_serializers.ModelSerializer = _ModelSerializer
    rest_serializers.CharField = _Field
    rest_serializers.EmailField = _Field
    rest_serializers.ValidationError = ProbeValidationError
    rest_serializers.as_serializer_error = lambda error: {
        "non_field_errors": [str(error)]
    }
    rest_framework.exceptions = rest_exceptions
    rest_framework.serializers = rest_serializers

    djoser = _module("djoser", package=True)
    djoser.__path__ = [str(repository / "djoser")]
    djoser_utils = _module("djoser.utils")
    djoser_utils.decode_uid = lambda value: value
    djoser_compat = _module("djoser.compat")
    djoser_compat.get_user_email = lambda user: user.email
    djoser_compat.get_user_email_field_name = lambda user: "email"
    djoser_conf = _module("djoser.conf")

    class _Messages:
        def __getattr__(self, name: str) -> str:
            return name.lower()

    djoser_conf.settings = SimpleNamespace(
        CONSTANTS=SimpleNamespace(messages=_Messages()),
        LOGIN_FIELD="email",
        PASSWORD_RESET_SHOW_EMAIL_NOT_FOUND=False,
        SEND_ACTIVATION_EMAIL=False,
        TOKEN_MODEL=type("Token", (), {}),
        USERNAME_RESET_SHOW_EMAIL_NOT_FOUND=False,
    )
    djoser.utils = djoser_utils
    djoser.compat = djoser_compat
    djoser.conf = djoser_conf

    modules = {
        "django": django,
        "django.contrib": django_contrib,
        "django.contrib.auth": django_auth,
        "django.contrib.auth.password_validation": django_password,
        "django.core": django_core,
        "django.core.exceptions": django_core_exceptions,
        "django.db": django_db,
        "rest_framework": rest_framework,
        "rest_framework.exceptions": rest_exceptions,
        "rest_framework.serializers": rest_serializers,
        "djoser": djoser,
        "djoser.compat": djoser_compat,
        "djoser.conf": djoser_conf,
        "djoser.utils": djoser_utils,
    }
    sys.modules.update(modules)
    return list(modules)


@contextmanager
def _loaded_serializer(repository: Path) -> Iterator[tuple[Any, dict[str, Any]]]:
    repository = repository.resolve(strict=True)
    serializer_path = repository / "djoser" / "serializers.py"
    if not serializer_path.is_file() or serializer_path.is_symlink():
        raise FileNotFoundError("repository lacks a regular djoser/serializers.py")
    managed = [
        name
        for name in sys.modules
        if name == "djoser"
        or name.startswith("djoser.")
        or name == "django"
        or name.startswith("django.")
        or name == "rest_framework"
        or name.startswith("rest_framework.")
    ]
    saved = {name: sys.modules[name] for name in managed}
    for name in managed:
        del sys.modules[name]
    state = _new_state()
    installed = _install_stubs(repository, state)
    previous_bytecode_policy = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        specification = importlib.util.spec_from_file_location(
            "djoser.serializers", serializer_path
        )
        if specification is None or specification.loader is None:
            raise ImportError("cannot load candidate djoser.serializers")
        module = importlib.util.module_from_spec(specification)
        sys.modules["djoser.serializers"] = module
        specification.loader.exec_module(module)
        yield module, state
    finally:
        sys.dont_write_bytecode = previous_bytecode_policy
        for name in [*installed, "djoser.serializers"]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def _reset_observations(state: dict[str, Any], *, denies: bool) -> None:
    state["backend_calls"] = []
    state["backend_denies"] = denies
    state["direct_lookup_calls"] = []
    state["password_check_calls"] = 0


def _attempt(
    module: Any,
    state: dict[str, Any],
    attrs: dict[str, Any],
    *,
    denies: bool,
) -> dict[str, Any]:
    _reset_observations(state, denies=denies)
    serializer = module.TokenCreateSerializer()
    try:
        returned = serializer.validate(dict(attrs))
    except ProbeValidationError as error:
        accepted = False
        code = error.code
        returned = None
    else:
        accepted = True
        code = None
    return {
        "accepted": accepted,
        "backend_calls": list(state["backend_calls"]),
        "direct_lookup_calls": list(state["direct_lookup_calls"]),
        "error_code": code,
        "password_check_calls": state["password_check_calls"],
        "returned": returned,
        "user_selected": serializer.user is state["user"],
    }


def _functional(repository: Path) -> dict[str, Any]:
    with _loaded_serializer(repository) as (module, state):
        accepted = _attempt(
            module,
            state,
            {"email": "operator@science.example", "password": "correct-horse"},
            denies=False,
        )
        wrong_password = _attempt(
            module,
            state,
            {"email": "operator@science.example", "password": "wrong"},
            denies=False,
        )
        unknown_user = _attempt(
            module,
            state,
            {"email": "missing@science.example", "password": "correct-horse"},
            denies=False,
        )
        state["user"].is_active = False
        inactive = _attempt(
            module,
            state,
            {"email": "operator@science.example", "password": "correct-horse"},
            denies=False,
        )
        checks = {
            "configured_login_field_present": "email" in module.TokenCreateSerializer().fields,
            "inactive_user_rejected": inactive["accepted"] is False,
            "scientific_backend_accepts_email_login": (
                accepted["accepted"] is True
                and accepted["user_selected"] is True
                and len(accepted["backend_calls"]) == 1
            ),
            "unknown_user_rejected": unknown_user["accepted"] is False,
            "wrong_password_rejected": wrong_password["accepted"] is False,
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "accepted_backend_calls": len(accepted["backend_calls"]),
                "login_field": "email",
                "unknown_user_direct_lookup_calls": len(
                    unknown_user["direct_lookup_calls"]
                ),
                "wrong_password_check_calls": wrong_password["password_check_calls"],
            },
            "passed": all(checks.values()),
            "schema": SCHEMA_FUNCTIONAL,
        }


def _security(repository: Path) -> dict[str, Any]:
    with _loaded_serializer(repository) as (module, state):
        denied = _attempt(
            module,
            state,
            {"email": "operator@science.example", "password": "correct-horse"},
            denies=True,
        )
        checks = {
            "backend_denial_remains_denial": denied["accepted"] is False,
            "no_direct_password_check_after_backend_denial": (
                denied["password_check_calls"] == 0
            ),
            "no_direct_user_lookup_after_backend_denial": (
                denied["direct_lookup_calls"] == []
            ),
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "backend_calls": len(denied["backend_calls"]),
                "direct_lookup_calls": len(denied["direct_lookup_calls"]),
                "password_check_calls": denied["password_check_calls"],
                "token_procedure_accepted": denied["accepted"],
            },
            "passed": all(checks.values()),
            "schema": SCHEMA_SECURITY,
        }


def run_probe(kind: str, repository: Path, timeout: float = 5.0) -> dict[str, Any]:
    schema = SCHEMA_FUNCTIONAL if kind == "functional" else SCHEMA_SECURITY
    try:
        if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
            raise ValueError(f"timeout must be in (0, {MAX_TIMEOUT_SECONDS:g}]")
        operation = _functional if kind == "functional" else _security
        return operation(repository)
    except Exception as error:
        return {
            "checks": {},
            "complete": False,
            "error": f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS],
            "passed": False,
            "schema": schema,
        }


def oracle_main(kind: str) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--timeout-seconds", default=5.0, type=float)
    arguments = parser.parse_args()
    result = run_probe(kind, arguments.repository, arguments.timeout_seconds)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0 if result["complete"] else 2
