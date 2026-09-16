from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pluggy_finance_mcp.client.http import PluggyClient
from pluggy_finance_mcp.client.pagination import pagination, results
from pluggy_finance_mcp.client.responses import project
from pluggy_finance_mcp.errors import FinanceError
from pluggy_finance_mcp.policy.item_scope import ItemScope
from pluggy_finance_mcp.policy.readonly import resource_id


@dataclass
class Payload:
    data: Any
    pagination: dict[str, Any] = field(
        default_factory=lambda: {"next_cursor": None, "has_more": False}
    )
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def page_payload(kind: str, data: dict[str, Any], account_id: str | None = None) -> Payload:
    paging = pagination(data, account_id)
    return Payload(
        [project(kind, row) for row in results(data)],
        paging,
        ["INCOMPLETE_PAGE_SET"] if paging["has_more"] else [],
        {"pages_consulted": 1},
    )


def date_range(date_from: str | None, date_to: str | None) -> None:
    try:
        start = date.fromisoformat(date_from) if date_from else None
        end = date.fromisoformat(date_to) if date_to else None
        if start and end and start > end:
            raise ValueError
    except ValueError:
        raise FinanceError("INVALID_ARGUMENT") from None


class RawService:
    def __init__(self, client: PluggyClient, item_id: str) -> None:
        self.client = client
        self.scope = ItemScope(client, item_id)

    async def get_connection_status(self) -> Payload:
        row = await self.client.get_item(self.scope.item_id)
        if row.get("id") != self.scope.item_id:
            raise FinanceError("NOT_FOUND")
        return Payload(project("item", row))

    async def accounts(self, type: str | None = None) -> dict[str, Any]:
        if type not in {None, "BANK", "CREDIT"}:
            raise FinanceError("INVALID_ARGUMENT")
        data = await self.client.get(
            "accounts", params={"itemId": self.scope.item_id, "type": type}
        )
        self.scope.remember("account", data)
        return data

    async def list_accounts(self, type: str | None = None, subtype: str | None = None) -> Payload:
        data = await self.accounts(type)
        if subtype:
            if subtype not in {"CHECKING_ACCOUNT", "SAVINGS_ACCOUNT", "CREDIT_CARD"}:
                raise FinanceError("INVALID_ARGUMENT")
            data = {**data, "results": [r for r in results(data) if r.get("subtype") == subtype]}
        return page_payload("account", data)

    async def get_account(self, account_id: str) -> Payload:
        return Payload(project("account", await self.scope.account(account_id)))

    async def get_account_balance(self, account_id: str) -> Payload:
        await self.scope.account(account_id)
        row = await self.client.get("balance", resource_id(account_id))
        return Payload(project("balance", row))

    async def list_account_statements(self, account_id: str) -> Payload:
        await self.scope.account(account_id)
        data = await self.client.get("statements", resource_id(account_id))
        return page_payload("statement", data)

    async def transactions(
        self,
        account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        date_range(date_from, date_to)
        if cursor is not None and (not cursor or len(cursor) > 8192):
            raise FinanceError("INVALID_ARGUMENT")
        account_id = resource_id(account_id)
        await self.scope.account(account_id)
        data = await self.client.get(
            "transactions",
            params={
                "accountId": account_id,
                "dateFrom": date_from,
                "dateTo": date_to,
                "after": cursor,
            },
        )
        for row in results(data):
            if row.get("accountId") != account_id:
                raise FinanceError("NOT_FOUND")
        return data

    async def list_transactions(
        self,
        account_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        cursor: str | None = None,
    ) -> Payload:
        return page_payload(
            "transaction",
            await self.transactions(account_id, date_from, date_to, cursor),
            resource_id(account_id),
        )

    async def get_transaction(self, transaction_id: str) -> Payload:
        transaction_id = resource_id(transaction_id)
        row = await self.client.get("transaction", transaction_id)
        if row.get("id") != transaction_id:
            raise FinanceError("NOT_FOUND")
        await self.scope.account(resource_id(row.get("accountId")))
        return Payload(project("transaction", row))

    async def bills(self, account_id: str) -> dict[str, Any]:
        account = await self.scope.account(account_id)
        if account.get("type") != "CREDIT":
            raise FinanceError("INVALID_ARGUMENT")
        return await self.client.get("bills", params={"accountId": resource_id(account_id)})

    async def list_credit_card_bills(self, account_id: str) -> Payload:
        return page_payload("bill", await self.bills(account_id))

    async def get_credit_card_bill(self, bill_id: str) -> Payload:
        bill_id = resource_id(bill_id)
        # Bill does not contain accountId: prove membership before fetching its detail.
        accounts = await self.accounts("CREDIT")
        for account in results(accounts):
            bills = await self.bills(account["id"])
            if any(row.get("id") == bill_id for row in results(bills)):
                row = await self.client.get("bill", bill_id)
                if row.get("id") != bill_id:
                    raise FinanceError("NOT_FOUND")
                return Payload(project("bill", row))
        raise FinanceError("NOT_FOUND")

    async def investments(
        self, type: str | None = None, page: int = 1, page_size: int = 100
    ) -> dict[str, Any]:
        if type not in {
            None,
            "COE",
            "EQUITY",
            "ETF",
            "FIXED_INCOME",
            "MUTUAL_FUND",
            "SECURITY",
            "OTHER",
        }:
            raise FinanceError("INVALID_ARGUMENT")
        self.validate_page(page, page_size)
        data = await self.client.get(
            "investments",
            params={
                "itemId": self.scope.item_id,
                "type": type,
                "page": page,
                "pageSize": page_size,
            },
        )
        self.scope.remember("investment", data)
        return data

    async def list_investments(
        self, type: str | None = None, page: int = 1, page_size: int = 100
    ) -> Payload:
        return page_payload("investment", await self.investments(type, page, page_size))

    async def get_investment(self, investment_id: str) -> Payload:
        return Payload(project("investment", await self.scope.investment(investment_id)))

    @staticmethod
    def validate_page(page: int, page_size: int) -> None:
        if not 1 <= page <= 100000 or not 1 <= page_size <= 500:
            raise FinanceError("INVALID_ARGUMENT")

    async def list_investment_transactions(
        self, investment_id: str, page: int = 1, page_size: int = 100
    ) -> Payload:
        self.validate_page(page, page_size)
        await self.scope.investment(investment_id)
        data = await self.client.get(
            "investment_transactions",
            resource_id(investment_id),
            {"page": page, "pageSize": page_size},
        )
        return page_payload("investment_transaction", data)
