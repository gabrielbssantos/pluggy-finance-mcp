from typing import Any
from urllib.parse import parse_qs, urlsplit

from pluggy_finance_mcp.errors import FinanceError


def pagination(data: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
    cursor = None
    if data.get("next"):
        try:
            parts = urlsplit(data["next"])
            if parts.scheme or parts.netloc or parts.path or parts.fragment:
                raise ValueError
            query = parse_qs(parts.query, strict_parsing=True)
            if set(query) - {"accountId", "after", "dateFrom", "dateTo", "createdAtFrom"}:
                raise ValueError
            if any(len(values) != 1 for values in query.values()):
                raise ValueError
            if "accountId" in query and query["accountId"][0] != account_id:
                raise ValueError
            cursor = query["after"][0]
            if not cursor or len(cursor) > 8192:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise FinanceError("UPSTREAM_ERROR") from None
    page = data.get("page")
    total_pages = data.get("totalPages")
    more_pages = bool(page is not None and total_pages is not None and page < total_pages)
    return {
        "next_cursor": cursor,
        "has_more": bool(cursor) or more_pages,
        "page": page,
        "total_pages": total_pages,
    }


def results(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("results")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise FinanceError("UPSTREAM_ERROR")
    return rows
