from decimal import Decimal
from typing import Any, Literal

Code = Literal[
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


class FinanceError(Exception):
    def __init__(
        self,
        code: str,
        retryable: bool = False,
        *,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status
        self.details = details or {}

    def public(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "retryable": self.retryable,
            "message": MESSAGES.get(self.code, "A operação Pluggy não foi concluída."),
            "httpStatus": self.http_status,
            **self.details,
        }


MESSAGES = {
    "ITEM_ALREADY_UPDATING": "Já existe uma sincronização em andamento.",
    "ITEM_IS_ALREADY_UPDATING": "Já existe uma sincronização em andamento.",
    "CLIENT_IS_UPDATING_BEFORE_ALLOWED_FREQUENCY": "Aguarde a frequência mínima contratada.",
    "SANDBOX_CLIENT_ITEM_UPDATE_NOT_ALLOWED": "O plano permite atualizar apenas Sandbox.",
    "CLIENT_HAS_ITEM_UPDATES_DISABLED": "Atualizações desabilitadas para esta aplicação Pluggy.",
    "CONNECTOR_OFFLINE": "A instituição/conector está temporariamente indisponível.",
    "INVALID_CREDENTIALS": "A conexão requer reautenticação via Pluggy Connect.",
    "LOGIN_ERROR": "A conexão requer reautenticação via Pluggy Connect.",
    "LAST_EXECUTION_HAD_LOGIN_ERROR": "A conexão requer reautenticação via Pluggy Connect.",
    "WAITING_USER_INPUT": "A conexão requer interação humana via Pluggy Connect.",
    "CONNECTOR_REQUIRED_PARAMETER_VALIDATION_ERROR": "Renove a conexão via Pluggy Connect.",
    "OUTDATED": "A última sincronização terminou com erro; os dados podem estar antigos.",
}


def upstream_error(status: int, data: dict[str, Any] | None = None) -> FinanceError:
    codes: dict[int, Code] = {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
        502: "UPSTREAM_UNAVAILABLE",
        503: "UPSTREAM_UNAVAILABLE",
        504: "UPSTREAM_TIMEOUT",
    }
    data = data or {}
    nested = data.get("error")
    source = nested if isinstance(nested, dict) else data
    candidates = [source.get("code"), source.get("errorCode"), nested]
    if isinstance(data.get("errors"), list):
        candidates.extend(row.get("code") for row in data["errors"] if isinstance(row, dict))
    code = next(
        (c for c in candidates if isinstance(c, str) and c in MESSAGES),
        codes.get(status, "UPSTREAM_ERROR"),
    )
    details = {}
    frequency = source.get("frequency")
    if (
        isinstance(frequency, (int, float, Decimal))
        and not isinstance(frequency, bool)
        and 0 < frequency <= 8760
    ):
        details["minimumUpdateIntervalHours"] = float(frequency)
    return FinanceError(
        code,
        code == "CONNECTOR_OFFLINE" or status in {429, 502, 503, 504},
        http_status=status,
        details=details,
    )
