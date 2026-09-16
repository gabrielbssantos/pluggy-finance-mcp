"""Deterministic catalog and transitive schema comparison, without importing app secrets."""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "patch", "delete", "put", "head", "options", "trace"}
OPTIONAL = {"GET /identity", "GET /identity/{id}"}
SANITIZATION_VERSION = 1
ANNOTATIONS = {"example", "examples", "x-readme", "x-codeSamples", "x-code-samples"}
NAMED_MAPS = {
    "properties",
    "patternProperties",
    "$defs",
    "definitions",
    "schemas",
    "paths",
    "responses",
    "parameters",
    "headers",
    "requestBodies",
    "securitySchemes",
    "links",
    "callbacks",
    "content",
    "encoding",
}


def sanitize_document(document: dict[str, Any]) -> dict[str, Any]:
    """Remove illustrative payloads, preserving contract names and literal constraints."""
    import copy

    def visit(value: Any, named_map: bool = False) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if not named_map and key in ANNOTATIONS:
                continue
            if not named_map and key in {"default", "enum", "const"}:
                result[key] = copy.deepcopy(item)
            else:
                result[key] = visit(item, not named_map and key in NAMED_MAPS)
        return result

    return visit(document)


def snapshot_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(sanitize_document(document), indent=2, sort_keys=True) + "\n").encode()


def operations(document: dict[str, Any]) -> dict[str, Any]:
    return {
        f"{method.upper()} {path}": operation
        for path, item in document["paths"].items()
        for method, operation in item.items()
        if method in METHODS
    }


def fingerprint(document: dict[str, Any], key: str) -> str:
    method, path = key.split(" ", 1)
    operation = document["paths"][path][method.lower()]
    included: dict[str, Any] = {
        "operation": operation,
        "path_parameters": document["paths"][path].get("parameters", []),
        "security": document.get("security"),
        "servers": document.get("servers"),
    }
    refs: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if ref and ref not in refs:
                if not ref.startswith("#/"):
                    raise ValueError("External references require manual review")
                refs.add(ref)
                resolved: Any = document
                for segment in ref[2:].split("/"):
                    resolved = resolved[segment.replace("~1", "/").replace("~0", "~")]
                included[ref] = resolved
                visit(resolved)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(dict(included))
    return hashlib.sha256(json.dumps(included, sort_keys=True).encode()).hexdigest()


def render(document: dict[str, Any], classifications: dict[str, Any], digest: str) -> str:
    ops = operations(document)
    lines = [
        "# Inventário de endpoints da Pluggy",
        "",
        "Gerado por `scripts/sync_openapi.py`; novas operações não habilitam tools.",
        "",
        f"Fonte: https://api.pluggy.ai/oas3.json · OpenAPI {document['openapi']} "
        f"· {len(ops)} operações.",
        f"SHA-256: `{digest}`",
        "",
        "| Método e caminho | operationId | Risco | MCP |",
        "|---|---|---|---|",
    ]
    for key, op in sorted(ops.items()):
        entry = classifications.get(key, {"risk": "UNCLASSIFIED", "scope": "excluded"})
        lines.append(
            f"| `{key}` | `{op.get('operationId', '')}` | {entry['risk']} | {entry['scope']} |"
        )
    lines += [
        "",
        "`enabled`: consultas e sincronização explícita de Item; "
        "`optional`: Identity não implementada;",
        "`internal`: autenticação exclusivamente interna; `excluded`: fora do MCP.",
        "R0: pública; R1: financeira; R2: altamente sensível; R3: administrativa; R4: pagamentos.",
        "",
    ]
    return "\n".join(lines)


def validate_document(document: dict[str, Any]) -> None:
    """Validate an unchanged snapshot with one narrow, reviewed upstream defect waiver."""
    import copy

    from openapi_spec_validator import validate

    checked = copy.deepcopy(document)
    exceptions = json.loads((ROOT / "openapi/validation-exceptions.json").read_text())
    for exception in exceptions:
        node = checked
        for key in exception["pointer"].lstrip("/").split("/"):
            node = node[key.replace("~1", "/").replace("~0", "~")]
        digest = hashlib.sha256(json.dumps(node, sort_keys=True).encode()).hexdigest()
        if digest == exception["schema_sha256"]:
            node.pop(exception["ignore_keyword"])
        # Changed schemas are validated without the waiver; upstream can fix the defect.
    validate(checked)


SOURCE = "https://api.pluggy.ai/oas3.json"


def fetch_document() -> bytes:
    import httpx

    with httpx.stream("GET", SOURCE, timeout=30, follow_redirects=False) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > 20_000_000:
                raise ValueError("OpenAPI too large")
    return bytes(content)


def validate_classifications(document: dict[str, Any], classes: dict[str, Any]) -> None:
    if set(operations(document)) != set(classes):
        raise ValueError("Catalog classification mismatch")
    for entry in classes.values():
        if entry.get("risk") not in {"R0", "R1", "R2", "R3", "R4"}:
            raise ValueError("UNCLASSIFIED operation requires review")
        if entry.get("scope") not in {"enabled", "optional", "internal", "excluded"}:
            raise ValueError("Invalid operation scope")
