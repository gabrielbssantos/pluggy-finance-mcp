import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from pluggy_finance_mcp.client.pagination import pagination, results
from pluggy_finance_mcp.client.responses import project
from pluggy_finance_mcp.errors import FinanceError
from pluggy_finance_mcp.policy.readonly import resource_id
from pluggy_finance_mcp.tools.classification import RULES_VERSION, classify
from pluggy_finance_mcp.tools.raw import Payload, RawService, date_range

TZ = ZoneInfo("America/Sao_Paulo")
SEMANTIC_TOOLS = {
    "get_total_balance",
    "get_monthly_expenses",
    "get_expenses_by_category",
    "get_credit_card_summary",
    "get_investment_portfolio",
    "get_net_worth",
}


def money(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def period(month: str | None, date_from: str | None, date_to: str | None) -> tuple[date, date]:
    try:
        if month and (date_from or date_to):
            raise ValueError
        if date_from or date_to:
            if not date_from or not date_to:
                raise ValueError
            date_range(date_from, date_to)
            return date.fromisoformat(date_from), date.fromisoformat(date_to)
        start = (
            date.fromisoformat(month + "-01") if month else datetime.now(TZ).date().replace(day=1)
        )
        if month and start.strftime("%Y-%m") != month:
            raise ValueError
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, next_month - timedelta(days=1)
    except ValueError:
        raise FinanceError("INVALID_ARGUMENT") from None


def ids(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    if not values or len(values) > 100:
        raise FinanceError("INVALID_ARGUMENT")
    return {resource_id(value) for value in values}


class BudgetStop(Exception):
    pass


class SemanticService:
    def __init__(self, raw: RawService) -> None:
        self.raw = raw
        self.settings = raw.client.settings
        self.pages = 0
        self.records = 0
        self.warnings: set[str] = set()
        self.accounts: list[dict[str, Any]] = []
        self.investments: list[dict[str, Any]] = []
        self.transactions: list[dict[str, Any]] = []
        self.bills: list[dict[str, Any]] = []
        self.seen: set[tuple[str, str]] = set()
        self.completed: list[str] = []

    def before_page(self) -> None:
        if self.pages >= self.settings.semantic_max_pages:
            self.warnings.add("PAGE_LIMIT")
            raise BudgetStop
        if self.records >= self.settings.semantic_max_records:
            self.warnings.add("RECORD_LIMIT")
            raise BudgetStop

    def accept(self, kind: str, response: dict[str, Any], target: list[dict[str, Any]]) -> None:
        self.pages += 1
        rows = results(response)
        if self.records + len(rows) > self.settings.semantic_max_records:
            self.warnings.add("RECORD_LIMIT_WHOLE_PAGE_OMITTED")
            raise BudgetStop
        self.records += len(rows)
        for row in rows:
            identifier = row.get("id")
            if not isinstance(identifier, str) or not identifier:
                self.warnings.add("MISSING_RECORD_ID")
                continue
            key = (kind, identifier)
            if key not in self.seen:
                target.append(row)
                self.seen.add(key)

    async def collect(
        self,
        tool: str,
        account_ids: set[str] | None,
        investment_ids: set[str] | None,
        dates: tuple[date, date] | None,
    ) -> None:
        if tool != "get_investment_portfolio":
            self.before_page()
            response = await self.raw.accounts()
            self.accept("account", response, self.accounts)
            if pagination(response)["has_more"]:
                self.warnings.add("ACCOUNTS_INCOMPLETE_NO_PAGING_CONTRACT")
            if account_ids is not None:
                available = {a["id"] for a in self.accounts}
                # Selected IDs absent from a truncated list must still be verified, not guessed.
                if not account_ids <= available:
                    raise FinanceError("NOT_FOUND")
                self.accounts = [a for a in self.accounts if a["id"] in account_ids]
            self.completed.append("accounts")
        if tool in {"get_investment_portfolio", "get_net_worth"}:
            page = 1
            while True:
                self.before_page()
                response = await self.raw.investments(page=page, page_size=100)
                self.accept("investment", response, self.investments)
                if not pagination(response)["has_more"]:
                    break
                page += 1
            if investment_ids is not None:
                if not investment_ids <= {i["id"] for i in self.investments}:
                    raise FinanceError("NOT_FOUND")
                self.investments = [i for i in self.investments if i["id"] in investment_ids]
            self.completed.append("investments")
        if dates:
            # Widen UTC date-only filters then apply the exact local window to every record.
            start, end = dates
            upper = (end + timedelta(days=1)).isoformat()
            for account in self.accounts:
                cursor = None
                cursors: set[str] = set()
                while True:
                    self.before_page()
                    response = await self.raw.transactions(
                        account["id"], start.isoformat(), upper, cursor
                    )
                    self.accept("transaction", response, self.transactions)
                    cursor = pagination(response, account["id"])["next_cursor"]
                    if not cursor:
                        break
                    if cursor in cursors:
                        self.warnings.add("REPEATED_CURSOR")
                        raise BudgetStop
                    cursors.add(cursor)
                self.completed.append("transactions:" + account["id"])
        if tool == "get_credit_card_summary":
            for account in self.accounts:
                if account.get("type") != "CREDIT":
                    continue
                self.before_page()
                response = await self.raw.bills(account["id"])
                rows: list[dict[str, Any]] = []
                self.accept("bill", response, rows)
                self.bills.extend({**row, "account_id": account["id"]} for row in rows)
                if pagination(response)["has_more"]:
                    self.warnings.add("BILLS_INCOMPLETE_NO_PAGING_CONTRACT")
                self.completed.append("bills:" + account["id"])

    async def run(
        self,
        tool: str,
        account_ids: list[str] | None = None,
        investment_ids: list[str] | None = None,
        month: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> Payload:
        selected_accounts, selected_investments = ids(account_ids), ids(investment_ids)
        dates = (
            period(month, date_from, date_to)
            if tool in {"get_monthly_expenses", "get_expenses_by_category"}
            else None
        )
        try:
            async with asyncio.timeout(self.settings.pluggy_http_timeout_seconds):
                await self.collect(tool, selected_accounts, selected_investments, dates)
        except BudgetStop:
            pass
        except TimeoutError:
            self.warnings.add("TIME_LIMIT")
        except FinanceError as error:
            if error.code in {"NOT_FOUND", "FORBIDDEN", "INVALID_ARGUMENT", "UNAUTHENTICATED"}:
                raise
            self.warnings.add(error.code)
        # Apply selection even if pagination was interrupted before completeness checks.
        if selected_accounts is not None:
            self.accounts = [a for a in self.accounts if a["id"] in selected_accounts]
        if selected_investments is not None:
            self.investments = [i for i in self.investments if i["id"] in selected_investments]
        if dates:
            data = self.expenses(*dates)
        elif tool == "get_credit_card_summary":
            data = {
                "bills": [
                    {**project("bill", row), "account_id": row["account_id"]} for row in self.bills
                ]
            }
        elif tool == "get_investment_portfolio":
            data = self.portfolio()
        elif tool == "get_net_worth":
            data = self.net_worth()
        else:
            data = self.balances()
        if not self.records:
            self.warnings.add("NO_DATA_AVAILABLE")
        timestamps = sorted(
            {
                str(row[key])
                for row in self.accounts + self.investments + self.transactions
                for key in ("updatedAt", "date")
                if row.get(key)
            }
        )
        meta = {
            "pages_consulted": self.pages,
            "records_consulted": self.records,
            "complete": not self.warnings,
            "completed_sources": self.completed,
            "timezone": str(TZ),
            "source_timestamps": timestamps,
            "period": {"from": dates[0].isoformat(), "to": dates[1].isoformat()} if dates else None,
            "rules_version": RULES_VERSION,
        }
        return Payload(data, warnings=sorted(self.warnings), meta=meta)

    def expenses(self, start: date, end: date) -> dict[str, Any]:
        totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        categories: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        counts: dict[str, int] = defaultdict(int)
        account_types = {a["id"]: a.get("type", "") for a in self.accounts}
        lower = datetime.combine(start, time.min, TZ)
        upper = datetime.combine(end + timedelta(days=1), time.min, TZ)
        for row in self.transactions:
            try:
                timestamp = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                if not lower <= timestamp < upper:
                    continue
            except (ValueError, KeyError, TypeError):
                self.warnings.add("INVALID_TRANSACTION_DATE")
                continue
            classification = classify(row, account_types.get(row.get("accountId"), ""))
            amount, currency = money(row.get("amount")), row.get("currencyCode")
            counts[classification] += 1
            if amount is None or not currency:
                self.warnings.add("MISSING_AMOUNT_OR_CURRENCY")
                continue
            totals[(currency, classification)] += abs(amount)
            if classification in {"expense", "refund"}:
                categories[(currency, row.get("category") or "Uncategorized")] += abs(amount) * (
                    1 if classification == "expense" else -1
                )
        if counts["ambiguous"]:
            self.warnings.add("AMBIGUOUS_MOVEMENTS_EXCLUDED")
        currencies = sorted({currency for currency, _ in totals})
        return {
            "by_currency": [
                {
                    "currency": c,
                    "gross_expenses": str(totals[(c, "expense")]),
                    "refunds": str(totals[(c, "refund")]),
                    "net_expenses": str(totals[(c, "expense")] - totals[(c, "refund")]),
                    "pending": str(totals[(c, "pending")]),
                    "ambiguous": str(totals[(c, "ambiguous")]),
                    "excluded": {
                        k: str(totals[(c, k)])
                        for k in ("bill_payment", "own_transfer", "investment")
                    },
                }
                for c in currencies
            ],
            "categories": [
                {"currency": c, "category": k, "net_expenses": str(v)}
                for (c, k), v in sorted(categories.items())
            ],
            "classification_counts": dict(counts),
        }

    def grouped(
        self, rows: list[dict[str, Any]], *, investments: bool = False
    ) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
        for row in rows:
            amount, currency = money(row.get("balance")), row.get("currencyCode")
            if amount is None or not currency:
                self.warnings.add("MISSING_BALANCE_OR_CURRENCY")
                continue
            institution = (row.get("institution") or {}).get("name") or "unknown"
            if institution == "unknown":
                self.warnings.add("INSTITUTION_UNAVAILABLE")
            groups[(currency, institution, row.get("type") or "unknown")] += amount
        return [
            {"currency": c, "institution": i, "type": t, "balance": str(v)}
            for (c, i, t), v in sorted(groups.items())
        ]

    def balances(self) -> dict[str, Any]:
        bank = [a for a in self.accounts if a.get("type") == "BANK"]
        cards = [a for a in self.accounts if a.get("type") == "CREDIT"]
        return {
            "bank_balances": self.grouped(bank),
            "credit_cards": [project("account", a) for a in cards],
        }

    def portfolio(self) -> dict[str, Any]:
        active = [i for i in self.investments if i.get("status") == "ACTIVE"]
        other = [i for i in self.investments if i.get("status") != "ACTIVE"]
        if other:
            self.warnings.add("NON_ACTIVE_OR_UNKNOWN_INVESTMENTS_EXCLUDED")
        return {
            "groups": self.grouped(active, investments=True),
            "positions": [project("investment", i) for i in active],
            "excluded_positions": [project("investment", i) for i in other],
        }

    def net_worth(self) -> dict[str, Any]:
        bank: dict[str, Decimal] = defaultdict(Decimal)
        invested: dict[str, Decimal] = defaultdict(Decimal)
        debt: dict[str, Decimal] = defaultdict(Decimal)
        missing: dict[str, set[str]] = {"bank": set(), "investments": set(), "debt": set()}
        unknown_currency = False
        currencies: set[str] = set()
        for row in self.accounts:
            value, currency = money(row.get("balance")), row.get("currencyCode")
            kind = "bank" if row.get("type") == "BANK" else "debt"
            if not currency:
                unknown_currency = True
                self.warnings.add("UNKNOWN_BALANCE_OR_DEBT")
                continue
            currencies.add(currency)
            if value is None or row.get("type") not in {"BANK", "CREDIT"}:
                missing[kind].add(currency)
                self.warnings.add("UNKNOWN_BALANCE_OR_DEBT")
                continue
            if kind == "bank":
                bank[currency] += value
            else:
                # Credit balance is the open invoice / used limit, never available credit.
                debt[currency] += value
                self.warnings.add("CARD_BALANCE_MAY_NOT_INCLUDE_PREVIOUS_INVOICES")
                foreign = money((row.get("creditData") or {}).get("balanceForeignCurrency"))
                if foreign is not None and foreign != 0:
                    self.warnings.add("FOREIGN_CARD_BALANCE_NOT_CONVERTED")
            auto = money((row.get("bankData") or {}).get("automaticallyInvestedBalance"))
            if auto is not None and auto > 0:
                self.warnings.add("POSSIBLE_ACCOUNT_INVESTMENT_OVERLAP")
        for row in self.investments:
            value, currency = money(row.get("balance")), row.get("currencyCode")
            if not currency:
                unknown_currency = True
                self.warnings.add("INVESTMENT_VALUATION_INCOMPLETE")
                continue
            currencies.add(currency)
            if row.get("status") == "TOTAL_WITHDRAWAL":
                continue
            if row.get("status") != "ACTIVE" or value is None:
                missing["investments"].add(currency)
                self.warnings.add("INVESTMENT_VALUATION_INCOMPLETE")
                continue
            invested[currency] += value
        if self.accounts and self.investments:
            self.warnings.add("ACCOUNT_INVESTMENT_OVERLAP_NOT_VERIFIABLE")
        self.warnings.add("LIMITED_TO_AVAILABLE_PRODUCTS_NO_LOANS_OR_EXTERNAL_ASSETS")
        account_coverage = (
            "accounts" in self.completed
            and "ACCOUNTS_INCOMPLETE_NO_PAGING_CONTRACT" not in self.warnings
        )
        investment_coverage = "investments" in self.completed
        estimates = []
        for currency in sorted(currencies):
            known_bank = account_coverage and currency not in missing["bank"]
            known_debt = account_coverage and currency not in missing["debt"]
            known_invested = investment_coverage and currency not in missing["investments"]
            valued = known_bank and known_debt and known_invested and not unknown_currency
            estimates.append(
                {
                    "currency": currency,
                    "bank_balance": str(bank[currency]) if known_bank else None,
                    "investments": str(invested[currency]) if known_invested else None,
                    "credit_card_debt": str(debt[currency]) if known_debt else None,
                    "estimated_net_worth": (
                        str(bank[currency] + invested[currency] - debt[currency])
                        if valued
                        else None
                    ),
                }
            )
        return {
            "estimates": estimates,
            "accounts": [project("account", a) for a in self.accounts],
            "investments": [project("investment", i) for i in self.investments],
            "complete": False,
        }
