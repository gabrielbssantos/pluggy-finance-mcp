import argparse
import hashlib
import json
from datetime import UTC, datetime

from openapi_catalog import (
    ROOT,
    SANITIZATION_VERSION,
    SOURCE,
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
    parser.add_argument(
        "--accept", action="store_true", help="Explicitly accept reviewed upstream changes"
    )
    args = parser.parse_args()
    target = ROOT / "openapi/pluggy-oas3.json"
    content = fetch_document()
    current = sanitize_document(json.loads(content))
    validate_document(current)
    old = sanitize_document(json.loads(target.read_bytes())) if target.exists() else {"paths": {}}
    old_ops, new_ops = operations(old), operations(current)
    classification_path = ROOT / "openapi/classifications.json"
    classifications = json.loads(classification_path.read_text())
    report = {
        "added": sorted(new_ops.keys() - old_ops.keys()),
        "removed": sorted(old_ops.keys() - new_ops.keys()),
        "changed": [
            key
            for key in sorted(old_ops.keys() & new_ops.keys())
            if fingerprint(old, key) != fingerprint(current, key)
        ],
    }
    print(json.dumps(report, indent=2))
    if not args.accept:
        raise SystemExit(1 if any(report.values()) else 0)
    if new_ops.keys() - classifications.keys():
        raise SystemExit("UNCLASSIFIED: classify new operations before accepting")
    validate_classifications(current, classifications)
    published = snapshot_bytes(current)
    digest = hashlib.sha256(published).hexdigest()
    target.write_bytes(published)
    (ROOT / "openapi/pluggy-oas3.sha256").write_text(digest + "\n")
    (ROOT / "openapi/metadata.json").write_text(
        json.dumps(
            {
                "source": SOURCE,
                "fetched_at": datetime.now(UTC).isoformat(),
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "snapshot_sha256": digest,
                "sanitization_version": SANITIZATION_VERSION,
                "diff": report,
            },
            indent=2,
        )
        + "\n"
    )
    (ROOT / "docs/ENDPOINTS_PLUGGY.md").write_text(render(current, classifications, digest))


if __name__ == "__main__":
    main()
