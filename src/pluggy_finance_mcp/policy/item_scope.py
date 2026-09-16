"""Request-local ownership proofs: no cross-request sensitive-data cache."""

from typing import Any

from pluggy_finance_mcp.client.http import PluggyClient
from pluggy_finance_mcp.client.pagination import results
from pluggy_finance_mcp.errors import FinanceError
from pluggy_finance_mcp.policy.readonly import resource_id


class ItemScope:
    def __init__(self, client: PluggyClient, item_id: str) -> None:
        self.client = client
        self.item_id = resource_id(item_id)
        self.accounts: dict[str, dict[str, Any]] = {}
        self.investments: dict[str, dict[str, Any]] = {}

    def check_item(self, row: dict[str, Any]) -> None:
        if row.get("itemId") != self.item_id:
            raise FinanceError("NOT_FOUND")

    async def account(self, identifier: str) -> dict[str, Any]:
        identifier = resource_id(identifier)
        if identifier not in self.accounts:
            row = await self.client.get("account", identifier)
            self.check_item(row)
            if row.get("id") != identifier:
                raise FinanceError("NOT_FOUND")
            self.accounts[identifier] = row
        return self.accounts[identifier]

    async def investment(self, identifier: str) -> dict[str, Any]:
        identifier = resource_id(identifier)
        if identifier not in self.investments:
            row = await self.client.get("investment", identifier)
            self.check_item(row)
            if row.get("id") != identifier:
                raise FinanceError("NOT_FOUND")
            self.investments[identifier] = row
        return self.investments[identifier]

    def remember(self, kind: str, response: dict[str, Any]) -> None:
        target = self.accounts if kind == "account" else self.investments
        for row in results(response):
            self.check_item(row)
            target[resource_id(row.get("id"))] = row
