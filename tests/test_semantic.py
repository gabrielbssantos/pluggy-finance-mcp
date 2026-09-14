import asyncio
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from conftest import BANK, CARD, FOREIGN, account, page, transaction

from pluggy_finance_mcp.server import Runtime
from pluggy_finance_mcp.tools.classification import classify
from pluggy_finance_mcp.tools.semantic import money, period


def tx(index, **kwargs):
    return transaction(str(UUID(int=100 + index)), **kwargs)


async def test_monthly_purchase_basis_and_decimal(client_api):
    client, api = client_api
    api.transactions[BANK] = [
        tx(1, amount=-0.1),
        tx(2, amount=-0.2),
        tx(3, amount=-100, category="Credit card payment"),
        tx(4, amount=-500, category="Fixed Income Investment"),
        tx(5, amount=-200, category="Same person transfer"),
        tx(6, amount=-30, category=None),
        tx(7, amount=-40, category="Groceries", status="PENDING"),
        tx(8, amount=-5, currencyCode="USD"),
    ]
    api.transactions[CARD] = [
        tx(
            9,
            accountId=CARD,
            amount=10,
            creditCardMetadata={"installmentNumber": 2, "totalInstallments": 5, "totalAmount": 50},
        ),
        tx(10, accountId=CARD, amount=-2, type="CREDIT", operationType="ESTORNO"),
        tx(11, accountId=CARD, amount=-100, type="CREDIT", operationType="PAGAMENTO_FATURA"),
    ]
    result = await Runtime(client.settings, client).invoke("get_monthly_expenses", month="2026-09")
    assert result.ok
    brl = next(row for row in result.data["by_currency"] if row["currency"] == "BRL")
    assert Decimal(brl["gross_expenses"]) == Decimal("10.3")
    assert Decimal(brl["net_expenses"]) == Decimal("8.3")
    assert brl["pending"] == "40"
    assert brl["ambiguous"] == "30"
    assert brl["excluded"] == {"bill_payment": "200", "own_transfer": "200", "investment": "500"}
    assert result.data["by_currency"][1]["currency"] == "USD"
    assert result.meta["pages_consulted"] == 3
    assert not result.meta["complete"]
    assert "AMBIGUOUS_MOVEMENTS_EXCLUDED" in result.warnings


async def test_timezone_boundaries_and_duplicate_id(client_api):
    client, api = client_api
    api.accounts = [account()]
    inside = tx(2, date="2026-10-01T02:59:59Z")
    api.transactions[BANK] = [
        tx(1, date="2026-09-01T02:59:59Z"),
        inside,
        inside,
        tx(3, date="2026-09-01T03:00:00Z"),
        tx(4, date="2026-10-01T03:00:00Z"),
    ]
    result = await Runtime(client.settings, client).invoke("get_monthly_expenses", month="2026-09")
    assert result.data["by_currency"][0]["net_expenses"] == "20"
    req = next(r for r in api.requests if r.url.path == "/v2/transactions")
    assert req.url.params["dateFrom"] == "2026-09-01"
    assert req.url.params["dateTo"] == "2026-10-01"


async def test_pagination_and_repeated_cursor(client_api):
    client, api = client_api
    api.accounts = [account()]

    async def cursor_page(request):
        if request.url.path == "/v2/transactions":
            index = 2 if request.url.params.get("after") else 1
            return httpx.Response(
                200, json={"results": [tx(index)], "next": f"?accountId={BANK}&after=same%2Bcursor"}
            )

    api.override = cursor_page
    result = await Runtime(client.settings, client).invoke("get_monthly_expenses", month="2026-09")
    assert "REPEATED_CURSOR" in result.warnings
    assert result.data["by_currency"][0]["net_expenses"] == "20"
    assert result.meta["pages_consulted"] == 3


async def test_page_limit(client_api):
    client, api = client_api
    client.settings.semantic_max_pages = 2
    result = await Runtime(client.settings, client).invoke("get_monthly_expenses", month="2026-09")
    assert "PAGE_LIMIT" in result.warnings
    assert result.data["by_currency"][0]["net_expenses"] == "10"
    assert not result.meta["complete"]


async def test_record_limit_keeps_whole_pages(client_api):
    client, api = client_api
    client.settings.semantic_max_records = 3
    api.transactions[BANK] = [tx(1), tx(2)]
    result = await Runtime(client.settings, client).invoke("get_monthly_expenses", month="2026-09")
    assert "RECORD_LIMIT_WHOLE_PAGE_OMITTED" in result.warnings
    assert result.data["by_currency"] == []
    assert result.meta["records_consulted"] == 2


async def test_timeout_retains_previous_pages(client_api):
    client, api = client_api
    client.settings.pluggy_http_timeout_seconds = 0.03

    async def slow_card(request):
        if request.url.path == "/v2/transactions" and request.url.params["accountId"] == CARD:
            await asyncio.sleep(0.15)

    api.override = slow_card
    result = await Runtime(client.settings, client).invoke("get_monthly_expenses", month="2026-09")
    assert result.ok and "TIME_LIMIT" in result.warnings
    assert result.data["by_currency"][0]["net_expenses"] == "10"


async def test_portfolio_active_and_missing_values(client_api):
    client, api = client_api
    api.investments.extend(
        [
            {**api.investments[0], "id": str(UUID(int=200)), "status": "PENDING", "balance": 800},
            {**api.investments[0], "id": str(UUID(int=201)), "balance": None},
        ]
    )
    result = await Runtime(client.settings, client).invoke("get_investment_portfolio")
    assert result.data["groups"][0]["balance"] == "500"
    assert len(result.data["positions"]) == 2
    assert len(result.data["excluded_positions"]) == 1
    assert "MISSING_BALANCE_OR_CURRENCY" in result.warnings


async def test_net_worth_does_not_double_count_bills_or_credit_limit(client_api):
    client, api = client_api
    api.accounts[1]["creditData"] = {"availableCreditLimit": 9000, "creditLimit": 10000}
    api.bills.extend(
        [{**api.bills[0], "id": str(UUID(int=300)), "totalAmount": 5000, "dueDate": "2025-01-01"}]
    )
    result = await Runtime(client.settings, client).invoke("get_net_worth")
    assert result.data["estimates"][0]["estimated_net_worth"] == "1400"
    assert not result.data["complete"]
    assert not any(r.url.path == "/bills" for r in api.requests)
    assert "ACCOUNT_INVESTMENT_OVERLAP_NOT_VERIFIABLE" in result.warnings


async def test_selected_accounts(client_api):
    client, api = client_api
    result = await Runtime(client.settings, client).invoke(
        "get_monthly_expenses", month="2026-09", account_ids=[CARD]
    )
    assert result.data["by_currency"][0]["net_expenses"] == "20"
    assert all(
        r.url.params["accountId"] == CARD for r in api.requests if r.url.path == "/v2/transactions"
    )
    result = await Runtime(client.settings, client).invoke(
        "get_total_balance", account_ids=[FOREIGN]
    )
    assert result.error["code"] == "NOT_FOUND"


async def test_selected_investments_after_budget_stop(client_api):
    client, api = client_api
    client.settings.semantic_max_pages = 1

    async def multi(request):
        if request.url.path == "/investments":
            return httpx.Response(200, json=page(api.investments, totalPages=2))

    api.override = multi
    result = await Runtime(client.settings, client).invoke(
        "get_investment_portfolio", investment_ids=[FOREIGN]
    )
    assert result.data["positions"] == []
    assert "PAGE_LIMIT" in result.warnings


@pytest.mark.parametrize(
    "kwargs",
    [
        {"month": "2026-13"},
        {"month": "2026-09", "date_from": "2026-09-01"},
        {"date_from": "2026-09-01"},
        {"date_from": "2026-10-01", "date_to": "2026-09-01"},
    ],
)
def test_invalid_periods(kwargs):
    from pluggy_finance_mcp.errors import FinanceError

    with pytest.raises(FinanceError, match="INVALID_ARGUMENT"):
        period(kwargs.get("month"), kwargs.get("date_from"), kwargs.get("date_to"))


def test_amount_and_classifier():
    assert money(None) is None
    assert money("NaN") is None
    assert money("0.1") + money("0.2") == Decimal("0.3")
    assert (
        classify(transaction(category=None, description="Credit Card Payment"), "BANK")
        == "ambiguous"
    )
    assert (
        classify(
            transaction(category=None, operationType="TRANSFERENCIA_MESMA_INSTITUICAO"), "BANK"
        )
        == "ambiguous"
    )


async def test_net_worth_unknown_is_not_zero(client_api):
    client, api = client_api
    api.accounts[0]["balance"] = None
    result = await Runtime(client.settings, client).invoke("get_net_worth")
    estimate = result.data["estimates"][0]
    assert estimate["bank_balance"] is None
    assert estimate["estimated_net_worth"] is None
    assert estimate["investments"] == "500"


async def test_net_worth_unfetched_investments_are_not_zero(client_api):
    client, api = client_api
    client.settings.semantic_max_pages = 1
    result = await Runtime(client.settings, client).invoke("get_net_worth")
    estimate = result.data["estimates"][0]
    assert estimate["investments"] is None
    assert estimate["estimated_net_worth"] is None
    assert "PAGE_LIMIT" in result.warnings


def test_structured_own_transfer_proof():
    person = {"documentNumber": {"type": "CPF", "value": "SYNTHETIC_DOCUMENT"}}
    row = transaction(
        category="Transfers",
        paymentData={"payer": person, "receiver": person, "paymentMethod": "PIX"},
    )
    assert classify(row, "BANK") == "own_transfer"
    assert classify(transaction(accountId=CARD, category="Transfers"), "CREDIT") == "ambiguous"
