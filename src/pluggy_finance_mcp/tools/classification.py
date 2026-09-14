"""Versioned, conservative rules; free-form descriptions never determine classification."""

from typing import Any

RULES_VERSION = "1.0.0"
EXCLUSIONS = {
    "Credit card payment": "bill_payment",
    "Credit Card Payment": "bill_payment",
    "Same person transfer": "own_transfer",
    "Same Person Transfer": "own_transfer",
    "Fixed Income Investment": "investment",
    "Investment": "investment",
    "Mutual Fund Investment": "investment",
    "Equity Investment": "investment",
}
EXPENSE_CATEGORIES = frozenset(
    {
        "Food",
        "Groceries",
        "Supermarket",
        "Restaurants",
        "Restaurant",
        "Shopping",
        "Transportation",
        "Transport",
        "Taxi",
        "Public transportation",
        "Fuel",
        "Gas Stations",
        "Education",
        "Health",
        "Healthcare",
        "Pharmacy",
        "Housing",
        "Rent",
        "Utilities",
        "Electricity",
        "Water",
        "Internet",
        "Telecommunications",
        "Entertainment",
        "Travel",
        "Insurance",
        "Taxes",
        "Fees",
        "Bank fees",
        "Personal care",
        "Clothing",
        "Services",
    }
)


def classify(row: dict[str, Any], account_type: str) -> str:
    category, operation = row.get("category"), row.get("operationType")
    if category in EXCLUSIONS:
        return EXCLUSIONS[category]
    if operation == "PAGAMENTO_FATURA" or (account_type == "CREDIT" and operation == "PAGAMENTO"):
        return "bill_payment"
    if operation in {"RESGATE_APLIC_FINANCEIRA", "RENDIMENTO_APLIC_FINANCEIRA"}:
        return "investment"
    payment = row.get("paymentData") or {}
    payer = (payment.get("payer") or {}).get("documentNumber") or {}
    receiver = (payment.get("receiver") or {}).get("documentNumber") or {}
    if (
        payer.get("value")
        and payer == receiver
        and payment.get("paymentMethod") in {"PIX", "TED", "DOC"}
    ):
        return "own_transfer"
    if category in {"Transfer", "Transfers", "Cash withdrawal", "Withdrawal"}:
        return "ambiguous"
    if operation == "TRANSFERENCIA_MESMA_INSTITUICAO":
        # Same institution alone does not establish the same owner.
        return "ambiguous"
    if row.get("status") == "PENDING":
        return "pending"
    if row.get("status") != "POSTED":
        return "ambiguous"
    if operation == "ESTORNO" and row.get("type") == "CREDIT":
        return "refund"
    if row.get("type") == "CREDIT":
        return "ambiguous"
    if row.get("type") != "DEBIT":
        return "ambiguous"
    if category in EXPENSE_CATEGORIES or operation in {
        "TARIFA",
        "TARIFA_SERVICOS_AVULSOS",
        "PACOTE_TARIFA_SERVICOS",
    }:
        return "expense"
    if account_type == "CREDIT" and operation not in {"OPERACOES_CREDITO_CONTRATADAS_CARTAO"}:
        return "expense"
    return "ambiguous"
