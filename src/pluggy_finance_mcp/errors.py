from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Literal

NormalizedCode = Literal[
    "INVALID_ARGUMENT",
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "NOT_FOUND",
    "RATE_LIMITED",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_ERROR",
    "CONFIGURATION_ERROR",
]


@dataclass(frozen=True, slots=True)
class ErrorPolicy:
    message: str
    retryable: bool = False
    requires_user_action: bool = False


_DEFAULT_MESSAGE = "A operação Pluggy não foi concluída."
ERROR_POLICIES: Mapping[str, ErrorPolicy] = MappingProxyType(
    {
        "INVALID_ARGUMENT": ErrorPolicy(_DEFAULT_MESSAGE),
        "UNAUTHENTICATED": ErrorPolicy(_DEFAULT_MESSAGE),
        "FORBIDDEN": ErrorPolicy(_DEFAULT_MESSAGE),
        "NOT_FOUND": ErrorPolicy(_DEFAULT_MESSAGE),
        "RATE_LIMITED": ErrorPolicy(_DEFAULT_MESSAGE, retryable=True),
        "UPSTREAM_TIMEOUT": ErrorPolicy(_DEFAULT_MESSAGE, retryable=True),
        "UPSTREAM_UNAVAILABLE": ErrorPolicy(_DEFAULT_MESSAGE, retryable=True),
        "UPSTREAM_ERROR": ErrorPolicy(_DEFAULT_MESSAGE),
        "CONFIGURATION_ERROR": ErrorPolicy(_DEFAULT_MESSAGE),
        "ITEM_ALREADY_UPDATING": ErrorPolicy(
            "Já existe uma sincronização em andamento.", retryable=True
        ),
        "ITEM_IS_ALREADY_UPDATING": ErrorPolicy(
            "Já existe uma sincronização em andamento.", retryable=True
        ),
        "PARAMETERS_NOT_PROVIDED": ErrorPolicy(
            "A conexão precisa ser renovada via Pluggy Connect.",
            requires_user_action=True,
        ),
        "CLIENT_IS_UPDATING_BEFORE_ALLOWED_FREQUENCY": ErrorPolicy(
            "Aguarde a frequência mínima contratada.", retryable=True
        ),
        "LAST_EXECUTION_HAD_LOGIN_ERROR": ErrorPolicy(
            "A conexão requer reautenticação via Pluggy Connect.",
            requires_user_action=True,
        ),
        "TOO_MANY_CONSECUTIVE_LOGIN_FAILURES": ErrorPolicy(
            "Muitas tentativas de login falharam; aguarde antes de tentar novamente.",
            retryable=True,
        ),
        "TOO_MANY_CONSECUTIVE_ERRORS": ErrorPolicy(
            "A conexão falhou repetidamente; contate o suporte da Pluggy.",
            requires_user_action=True,
        ),
        "ITEM_IN_ERROR_COOLDOWN": ErrorPolicy(
            "A conexão está em período de espera; tente novamente mais tarde.", retryable=True
        ),
        "CONNECTOR_OFFLINE": ErrorPolicy(
            "A instituição/conector está temporariamente indisponível.", retryable=True
        ),
        "CONNECTOR_REQUIRED_PARAMETER_VALIDATION_ERROR": ErrorPolicy(
            "Renove a conexão via Pluggy Connect.", requires_user_action=True
        ),
        "ITEM_ORIGINAL_CONNECTED_WITH_DIFFERENT_ACCOUNT": ErrorPolicy(
            "Use a conta originalmente autorizada para renovar esta conexão.",
            requires_user_action=True,
        ),
        "ITEM_CREATION_LIMIT_EXCEEDED": ErrorPolicy(
            "O limite de Items do plano Pluggy foi atingido.", requires_user_action=True
        ),
        "CLIENT_HAS_ITEM_UPDATES_DISABLED": ErrorPolicy(
            "Atualizações desabilitadas para esta aplicação Pluggy.",
            requires_user_action=True,
        ),
        "CREATE_ITEMS_API_FREE_DISABLED": ErrorPolicy(
            "O plano exige o Pluggy Connect para criar Items.", requires_user_action=True
        ),
        "SANDBOX_CLIENT_ITEM_UPDATE_NOT_ALLOWED": ErrorPolicy(
            "O plano permite atualizar apenas Items Sandbox.", requires_user_action=True
        ),
        "INVALID_CREDENTIALS": ErrorPolicy(
            "A conexão requer reautenticação via Pluggy Connect.",
            requires_user_action=True,
        ),
        "LOGIN_ERROR": ErrorPolicy(
            "A conexão requer reautenticação via Pluggy Connect.",
            requires_user_action=True,
        ),
        "WAITING_USER_INPUT": ErrorPolicy(
            "A conexão requer interação humana via Pluggy Connect.",
            requires_user_action=True,
        ),
        "OUTDATED": ErrorPolicy(
            "A última sincronização terminou com erro; os dados podem estar antigos."
        ),
    }
)
_NORMALIZED_CODES = frozenset(
    {
        "INVALID_ARGUMENT",
        "UNAUTHENTICATED",
        "FORBIDDEN",
        "NOT_FOUND",
        "RATE_LIMITED",
        "UPSTREAM_TIMEOUT",
        "UPSTREAM_UNAVAILABLE",
        "UPSTREAM_ERROR",
        "CONFIGURATION_ERROR",
    }
)
_PLUGGY_ERROR_CODES = frozenset(ERROR_POLICIES).difference(_NORMALIZED_CODES)
USER_ACTION_CODES = frozenset(
    code for code, policy in ERROR_POLICIES.items() if policy.requires_user_action
)

HTTP_ERROR_CODES: Mapping[int, NormalizedCode] = MappingProxyType(
    {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
        502: "UPSTREAM_UNAVAILABLE",
        503: "UPSTREAM_UNAVAILABLE",
        504: "UPSTREAM_TIMEOUT",
    }
)


class FinanceError(Exception):
    def __init__(
        self,
        code: str,
        retryable: bool | None = None,
        *,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        policy = ERROR_POLICIES.get(code, ErrorPolicy(_DEFAULT_MESSAGE))
        self.code = code
        self.retryable = policy.retryable if retryable is None else retryable
        self.requires_user_action = policy.requires_user_action
        self.http_status = http_status
        self.details = details or {}

    def public(self) -> dict[str, Any]:
        policy = ERROR_POLICIES.get(self.code, ErrorPolicy(_DEFAULT_MESSAGE))
        return {
            "code": self.code,
            "retryable": self.retryable,
            "message": policy.message,
            "httpStatus": self.http_status,
            **self.details,
        }


def _known_error_code(data: dict[str, Any]) -> str | None:
    nested = data.get("error")
    objects = [data]
    if isinstance(nested, dict):
        objects.append(nested)
    errors = data.get("errors")
    if isinstance(errors, list):
        objects.extend(row for row in errors if isinstance(row, dict))

    for key in ("codeDescription", "code", "errorCode"):
        for source in objects:
            candidate = source.get(key)
            if isinstance(candidate, str) and candidate in _PLUGGY_ERROR_CODES:
                return candidate
    if isinstance(nested, str) and nested in _PLUGGY_ERROR_CODES:
        return nested
    return None


def _hours(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite() or not Decimal(0) < number <= Decimal(8760):
        return None
    return float(number)


def _minimum_update_interval(data: dict[str, Any]) -> float | None:
    nested = data.get("error")
    details = data.get("data")
    sources = [source for source in (details, nested, data) if isinstance(source, dict)]
    for key in ("minUpdateFrequencyAllowedInHours", "frequency"):
        for source in sources:
            value = _hours(source.get(key))
            if value is not None:
                return value
    return None


def upstream_error(status: int, data: dict[str, Any] | None = None) -> FinanceError:
    data = data or {}
    code = _known_error_code(data) or HTTP_ERROR_CODES.get(status, "UPSTREAM_ERROR")
    details: dict[str, Any] = {}
    frequency = _minimum_update_interval(data)
    if frequency is not None:
        details["minimumUpdateIntervalHours"] = frequency
    return FinanceError(code, http_status=status, details=details)
