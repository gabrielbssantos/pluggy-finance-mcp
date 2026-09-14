import argparse
import hashlib
import json

from openapi_catalog import (
    OPTIONAL,
    ROOT,
    SANITIZATION_VERSION,
    fetch_document,
    fingerprint,
    operations,
    render,
    sanitize_document,
    snapshot_bytes,
    validate_classifications,
    validate_document,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", action="store_true")
    args = parser.parse_args()
    raw = (ROOT / "openapi/pluggy-oas3.json").read_bytes()
    snapshot = json.loads(raw)
    if snapshot_bytes(snapshot) != raw:
        raise SystemExit("Snapshot must be sanitized and canonically serialized")
    validate_document(snapshot)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != (ROOT / "openapi/pluggy-oas3.sha256").read_text().strip():
        raise SystemExit("Snapshot hash mismatch")
    metadata = json.loads((ROOT / "openapi/metadata.json").read_text())
    if (
        metadata.get("snapshot_sha256") != digest
        or metadata.get("sanitization_version") != SANITIZATION_VERSION
        or len(metadata.get("source_sha256", "")) != 64
    ):
        raise SystemExit("Snapshot metadata mismatch")
    classes = json.loads((ROOT / "openapi/classifications.json").read_text())
    validate_classifications(snapshot, classes)
    if (ROOT / "docs/ENDPOINTS_PLUGGY.md").read_text() != render(snapshot, classes, digest):
        raise SystemExit("Generated inventory is stale")
    if not args.remote:
        print("Snapshot and catalog valid")
        return
    raw = fetch_document()
    remote = sanitize_document(json.loads(raw))
    validate_document(remote)
    before, after = operations(snapshot), operations(remote)
    changes = {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": [
            key
            for key in sorted(before.keys() & after.keys())
            if fingerprint(snapshot, key) != fingerprint(remote, key)
        ],
    }
    protected = OPTIONAL | {
        key for key, entry in classes.items() if entry["scope"] in {"enabled", "internal"}
    }
    blocking = bool(
        changes["added"] or changes["removed"] or protected.intersection(changes["changed"])
    )
    print(json.dumps({**changes, "blocking": blocking}, indent=2))
    raise SystemExit(1 if blocking else 0)


if __name__ == "__main__":
    main()
