import copy
import json
import sys
from pathlib import Path

import pytest
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

from pluggy_finance_mcp.client.responses import FIELDS
from pluggy_finance_mcp.policy.readonly import OPERATIONS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from openapi_catalog import fingerprint, operations, validate_document  # noqa: E402


def document():
    return json.loads((ROOT / "openapi/pluggy-oas3.json").read_text())


def test_snapshot_and_runtime_allowlist():
    doc = document()
    validate_document(doc)
    classes = json.loads((ROOT / "openapi/classifications.json").read_text())
    assert len(OPERATIONS) == 12
    assert set(classes) == set(operations(doc))
    assert {key for key, row in classes.items() if row["scope"] == "enabled"} == {
        "GET " + op.path for op in OPERATIONS.values()
    }
    for op in OPERATIONS.values():
        current = doc["paths"][op.path]["get"]
        allowed = {p["name"] for p in current.get("parameters", []) if p["in"] == "query"}
        assert op.params <= allowed
    assert "/transactions" not in {op.path for op in OPERATIONS.values()}


@pytest.mark.parametrize(
    "kind,schema",
    [
        ("account", "Account"),
        ("transaction", "Transaction"),
        ("investment", "Investment"),
        ("bill", "Bill"),
        ("item", "Item"),
    ],
)
def test_projections_only_documented_fields(kind, schema):
    assert FIELDS[kind] <= document()["components"]["schemas"][schema]["properties"].keys()


def test_transitive_schema_drift_detected():
    before = document()
    after = copy.deepcopy(before)
    after["components"]["schemas"]["Account"]["properties"]["balance"]["type"] = "string"
    assert fingerprint(before, "GET /accounts") != fingerprint(after, "GET /accounts")
    assert fingerprint(before, "GET /items/{id}") == fingerprint(after, "GET /items/{id}")


def test_waiver_does_not_hide_new_defects():
    doc = document()
    doc["components"]["schemas"]["Account"]["properties"]["balance"]["default"] = "invalid-number"
    with pytest.raises(OpenAPIValidationError):
        validate_document(doc)
