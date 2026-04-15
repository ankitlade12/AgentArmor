import inspect

import agentarmor.exceptions as exceptions
from agentarmor.exceptions import (
    SHIELD_EXCEPTIONS,
    HookError,
    PatchError,
    ConfigurationError,
)


def test_shield_exceptions_tuple_is_non_empty():
    assert isinstance(SHIELD_EXCEPTIONS, tuple)
    assert len(SHIELD_EXCEPTIONS) >= 25


def test_shield_exceptions_members_subclass_exception():
    for exc_cls in SHIELD_EXCEPTIONS:
        assert issubclass(exc_cls, Exception)


def test_shield_exceptions_excludes_infrastructure_errors():
    assert HookError not in SHIELD_EXCEPTIONS
    assert PatchError not in SHIELD_EXCEPTIONS


def test_shield_exceptions_excludes_configuration_error():
    assert ConfigurationError not in SHIELD_EXCEPTIONS


def test_shield_exceptions_in_sync_with_declared_classes():
    declared = {
        name
        for name, obj in inspect.getmembers(exceptions, inspect.isclass)
        if obj.__module__ == "agentarmor.exceptions"
        and issubclass(obj, Exception)
        and name not in {"HookError", "PatchError", "ConfigurationError"}
    }
    registered = {cls.__name__ for cls in SHIELD_EXCEPTIONS}
    missing = declared - registered
    extra = registered - declared
    assert not missing, f"shield exceptions declared but not in SHIELD_EXCEPTIONS: {missing}"
    assert not extra, f"SHIELD_EXCEPTIONS contains classes not declared in exceptions.py: {extra}"


def test_shield_exceptions_isinstance_check_works():
    err = exceptions.InjectionDetected("test")
    assert isinstance(err, SHIELD_EXCEPTIONS)

    not_a_shield = HookError("test")
    assert not isinstance(not_a_shield, SHIELD_EXCEPTIONS)

    not_a_shield_2 = ConfigurationError("test")
    assert not isinstance(not_a_shield_2, SHIELD_EXCEPTIONS)
