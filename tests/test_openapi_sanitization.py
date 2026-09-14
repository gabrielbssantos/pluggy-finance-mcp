import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from openapi_catalog import (  # noqa: E402
    ROOT,
    fingerprint,
    operations,
    sanitize_document,
    snapshot_bytes,
    validate_document,
)


def test_sanitization_preserves_contract_and_does_not_mutate():
    document = {
        "paths": {
            "/demo": {
                "get": {
                    "parameters": [
                        {
                            "name": "example",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "integer", "default": 3},
                            "example": "synthetic-sensitive-value",
                        }
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/examples"},
                                    "examples": {"sample": {"value": "synthetic-sensitive-value"}},
                                }
                            }
                        }
                    },
                    "x-readme": {"code-samples": ["synthetic-sensitive-value"]},
                    "x-codeSamples": [{"source": "synthetic-sensitive-value"}],
                    "x-code-samples": [{"source": "synthetic-sensitive-value"}],
                }
            }
        },
        "components": {
            "schemas": {
                "examples": {
                    "type": "object",
                    "required": ["example", "examples"],
                    "properties": {
                        name: {"type": "string", "example": "synthetic-sensitive-value"}
                        for name in ["example", "examples", "x-readme"]
                    },
                }
            }
        },
    }
    original = copy.deepcopy(document)
    clean = sanitize_document(document)
    assert document == original
    assert sanitize_document(clean) == clean
    assert "synthetic-sensitive-value" not in json.dumps(clean)
    assert operations(clean).keys() == operations(document).keys()
    schema = clean["components"]["schemas"]["examples"]
    assert schema["required"] == ["example", "examples"]
    assert schema["properties"] == {
        k: {"type": "string"} for k in ["example", "examples", "x-readme"]
    }
    assert clean["paths"]["/demo"]["get"]["parameters"] == [
        {
            "name": "example",
            "in": "query",
            "required": True,
            "schema": {"type": "integer", "default": 3},
        }
    ]


def test_literal_constraints_are_not_annotations():
    doc = {
        "type": "object",
        "default": {"example": "required literal"},
        "enum": [{"examples": "required literal"}],
        "const": {"x-readme": "literal"},
    }
    assert sanitize_document(doc) == doc


def test_canonical_serialization_is_order_independent():
    assert snapshot_bytes({"paths": {}, "openapi": "3.1.0"}) == snapshot_bytes(
        {"openapi": "3.1.0", "paths": {}, "example": "discard"}
    )


def test_examples_do_not_drift_but_contract_changes_do():
    doc = json.loads((ROOT / "openapi/pluggy-oas3.json").read_bytes())
    changed = copy.deepcopy(doc)
    balance = changed["components"]["schemas"]["Account"]["properties"]["balance"]
    balance["example"] = "synthetic-sensitive-value"
    assert fingerprint(doc, "GET /accounts") == fingerprint(
        sanitize_document(changed), "GET /accounts"
    )
    balance["type"] = "string"
    assert fingerprint(doc, "GET /accounts") != fingerprint(
        sanitize_document(changed), "GET /accounts"
    )


def test_published_snapshot_is_sanitized_valid_and_resources_excluded():
    raw = (ROOT / "openapi/pluggy-oas3.json").read_bytes()
    doc = json.loads(raw)
    assert snapshot_bytes(doc) == raw
    validate_document(doc)
    classes = json.loads((ROOT / "openapi/classifications.json").read_bytes())
    assert classes["GET /items/{id}/resources"]["scope"] == "excluded"
    coverage = doc["components"]["schemas"]["Connector"]["properties"]["productCoverage"]
    assert coverage["type"] == "array"
