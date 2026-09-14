from dataclasses import dataclass
from uuid import UUID

from pluggy_finance_mcp.errors import FinanceError


@dataclass(frozen=True)
class Operation:
    path: str
    params: frozenset[str] = frozenset()


OPERATIONS = {
    "item": Operation("/items/{id}"),
    "accounts": Operation("/accounts", frozenset({"itemId", "type"})),
    "account": Operation("/accounts/{id}"),
    "statements": Operation("/accounts/{id}/statements"),
    "balance": Operation("/accounts/{id}/balance"),
    "transactions": Operation(
        "/v2/transactions", frozenset({"accountId", "dateFrom", "dateTo", "after"})
    ),
    "transaction": Operation("/transactions/{id}"),
    "bills": Operation("/bills", frozenset({"accountId"})),
    "bill": Operation("/bills/{id}"),
    "investments": Operation("/investments", frozenset({"itemId", "type", "page", "pageSize"})),
    "investment": Operation("/investments/{id}"),
    "investment_transactions": Operation(
        "/investments/{id}/transactions", frozenset({"page", "pageSize"})
    ),
}


def resource_id(value: object) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise FinanceError("INVALID_ARGUMENT") from None


def resolve(operation: str, identifier: str | None, params: dict[str, object], method: str) -> str:
    if method != "GET" or operation not in OPERATIONS:
        raise FinanceError("FORBIDDEN")
    spec = OPERATIONS[operation]
    if not params.keys() <= spec.params:
        raise FinanceError("INVALID_ARGUMENT")
    if "{id}" in spec.path:
        return spec.path.format(id=resource_id(identifier))
    if identifier is not None:
        raise FinanceError("INVALID_ARGUMENT")
    return spec.path
