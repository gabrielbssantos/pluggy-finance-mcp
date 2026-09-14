"""Explicit projections: upstream text is data, never server instructions."""

from typing import Any

COMMON = {"id", "type", "subtype", "name", "balance", "currencyCode", "createdAt", "updatedAt"}
FIELDS = {
    "item": {
        "id",
        "status",
        "executionStatus",
        "createdAt",
        "updatedAt",
        "lastUpdatedAt",
        "nextAutoSyncAt",
        "consentExpiresAt",
        "products",
    },
    "account": COMMON | {"marketingName"},
    "balance": {
        "balance",
        "blockedBalance",
        "automaticallyInvestedBalance",
        "currencyCode",
        "updateDateTime",
    },
    "transaction": (COMMON - {"name", "subtype"})
    | {
        "description",
        "amount",
        "amountInAccountCurrency",
        "date",
        "status",
        "category",
        "categoryId",
        "accountId",
        "operationType",
    },
    "investment": COMMON
    | {
        "code",
        "isin",
        "value",
        "quantity",
        "amount",
        "taxes",
        "taxes2",
        "date",
        "status",
        "amountProfit",
        "amountWithdrawal",
        "amountOriginal",
        "dueDate",
        "issuer",
        "purchaseDate",
        "rate",
        "rateType",
        "fixedAnnualRate",
        "annualRate",
    },
    "investment_transaction": {
        "id",
        "amount",
        "description",
        "value",
        "quantity",
        "tradeDate",
        "date",
        "type",
        "movementType",
        "netAmount",
        "agreedRate",
    },
    "bill": {
        "id",
        "dueDate",
        "billClosingDate",
        "totalAmount",
        "totalAmountCurrencyCode",
        "minimumPaymentAmount",
        "allowsInstallments",
    },
    "statement": {"id", "monthYear", "url"},
}
NESTED = {
    "account": {
        "bankData": {
            "closingBalance",
            "automaticallyInvestedBalance",
            "overdraftContractedLimit",
            "overdraftUsedLimit",
            "unarrangedOverdraftAmount",
        },
        "creditData": {
            "level",
            "brand",
            "balanceCloseDate",
            "balanceDueDate",
            "availableCreditLimit",
            "balanceForeignCurrency",
            "minimumPayment",
            "creditLimit",
            "status",
        },
    },
    "transaction": {
        "creditCardMetadata": {
            "installmentNumber",
            "totalInstallments",
            "totalAmount",
            "billId",
            "purchaseDate",
            "billForecastDate",
            "feeType",
        }
    },
    "investment": {"institution": {"name"}},
    "item": {"connector": {"name", "products"}, "error": {"code"}},
    "bill": {
        "payments": {"valueType", "paymentDate", "paymentMode", "amount", "currencyCode"},
        "financeCharges": {"type", "amount", "currencyCode"},
    },
}


def project(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    result = {k: v for k, v in row.items() if k in FIELDS[kind] and not isinstance(v, (dict, list))}
    for key, fields in NESTED.get(kind, {}).items():
        value = row.get(key)
        if isinstance(value, dict):
            result[key] = {
                k: v for k, v in value.items() if k in fields and not isinstance(v, (dict, list))
            }
        elif isinstance(value, list):
            result[key] = [
                {k: v for k, v in item.items() if k in fields and not isinstance(v, (dict, list))}
                for item in value
                if isinstance(item, dict)
            ]
    return result
