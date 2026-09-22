from decimal import Decimal

import pytest

from pluggy_finance_mcp.errors import ERROR_POLICIES, FinanceError, upstream_error


@pytest.mark.parametrize(
    "status,code,retryable,requires_user_action",
    [
        (400, "PARAMETERS_NOT_PROVIDED", False, True),
        (400, "LAST_EXECUTION_HAD_LOGIN_ERROR", False, True),
        (400, "TOO_MANY_CONSECUTIVE_LOGIN_FAILURES", True, False),
        (400, "TOO_MANY_CONSECUTIVE_ERRORS", False, True),
        (409, "ITEM_IN_ERROR_COOLDOWN", True, False),
        (409, "CONNECTOR_OFFLINE", True, False),
        (400, "CONNECTOR_REQUIRED_PARAMETER_VALIDATION_ERROR", False, True),
        (409, "ITEM_ORIGINAL_CONNECTED_WITH_DIFFERENT_ACCOUNT", False, True),
        (409, "ITEM_CREATION_LIMIT_EXCEEDED", False, True),
        (409, "CLIENT_HAS_ITEM_UPDATES_DISABLED", False, True),
        (400, "CREATE_ITEMS_API_FREE_DISABLED", False, True),
        (400, "SANDBOX_CLIENT_ITEM_UPDATE_NOT_ALLOWED", False, True),
    ],
)
def test_official_pluggy_error_shape(status, code, retryable, requires_user_action):
    error = upstream_error(
        status,
        {
            "code": status,
            "codeDescription": code,
            "message": "PRIVATE_UPSTREAM_MESSAGE",
            "providerMessage": "PRIVATE_PROVIDER_MESSAGE",
            "data": {"private": "PRIVATE_DATA"},
        },
    )

    assert error.code == code
    assert error.retryable is retryable
    assert error.requires_user_action is requires_user_action
    assert "PRIVATE" not in str(error.public())


@pytest.mark.parametrize("field", ["code", "errorCode"])
def test_legacy_string_codes_remain_compatible(field):
    error = upstream_error(400, {field: "ITEM_ALREADY_UPDATING"})
    assert error.code == "ITEM_ALREADY_UPDATING"
    assert error.retryable


def test_official_code_description_takes_precedence_over_legacy_fields():
    error = upstream_error(
        400,
        {
            "codeDescription": "PARAMETERS_NOT_PROVIDED",
            "code": "ITEM_ALREADY_UPDATING",
            "errorCode": "CONNECTOR_OFFLINE",
        },
    )
    assert error.code == "PARAMETERS_NOT_PROVIDED"


@pytest.mark.parametrize(
    "value,expected",
    [
        (24, 24.0),
        (1.5, 1.5),
        (Decimal("0.25"), 0.25),
    ],
)
def test_frequency_is_extracted_from_official_data(value, expected):
    error = upstream_error(
        409,
        {
            "code": 409,
            "codeDescription": "CLIENT_IS_UPDATING_BEFORE_ALLOWED_FREQUENCY",
            "data": {"minUpdateFrequencyAllowedInHours": value},
        },
    )
    assert error.details == {"minimumUpdateIntervalHours": expected}
    assert error.retryable


def test_legacy_frequency_remains_compatible():
    error = upstream_error(
        409,
        {
            "code": "CLIENT_IS_UPDATING_BEFORE_ALLOWED_FREQUENCY",
            "frequency": 12,
        },
    )
    assert error.details == {"minimumUpdateIntervalHours": 12.0}


@pytest.mark.parametrize(
    "value",
    [None, True, "24", 0, -1, 8761, float("inf"), float("nan"), Decimal("NaN")],
)
def test_invalid_frequency_is_ignored(value):
    error = upstream_error(
        409,
        {
            "codeDescription": "CLIENT_IS_UPDATING_BEFORE_ALLOWED_FREQUENCY",
            "data": {"minUpdateFrequencyAllowedInHours": value},
        },
    )
    assert error.details == {}


def test_unknown_or_malformed_codes_fall_back_without_leaking():
    for payload in [
        {"code": 400, "codeDescription": "PRIVATE_UNKNOWN", "message": "PRIVATE_MESSAGE"},
        {"code": 400, "codeDescription": "UNAUTHENTICATED", "message": "PRIVATE_MESSAGE"},
        {"codeDescription": ["ITEM_ALREADY_UPDATING"], "providerMessage": "PRIVATE_MESSAGE"},
        {"error": {"codeDescription": "PRIVATE_UNKNOWN", "private": "PRIVATE_DATA"}},
    ]:
        error = upstream_error(400, payload)
        assert error.code == "INVALID_ARGUMENT"
        assert error.public() == {
            "code": "INVALID_ARGUMENT",
            "retryable": False,
            "message": "A operação Pluggy não foi concluída.",
            "httpStatus": 400,
        }


def test_error_policy_is_immutable_and_unknown_finance_error_is_safe():
    with pytest.raises(TypeError):
        ERROR_POLICIES["PRIVATE"] = ERROR_POLICIES["UPSTREAM_ERROR"]  # type: ignore[index]

    error = FinanceError("PRIVATE_UNKNOWN")
    assert error.public()["message"] == "A operação Pluggy não foi concluída."
    assert "PRIVATE_UNKNOWN" not in error.public()["message"]
