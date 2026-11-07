#!/usr/bin/env python3
"""Generate an OpenVEX document for CVEs fixed by backport.

A backported fix does not change the package version string, so a scanner that
matches on version alone keeps reporting the CVE even though the source is
patched. VEX ("Vulnerability Exploitability eXchange") is the standard way to
tell the scanner "this one is handled": we assert status `fixed` and the scanner
moves it to its ignore list.

The one wrinkle is matching. Grype applies a VEX statement to a finding when the
statement's *product* identifies the scanned image and its *subcomponent*
identifies the vulnerable package. A locally built image was never pushed to a
registry, so it has no single canonical reference; Grype may know it by its tag,
its image ID, or its manifest digest. Rather than guess, this script reads the
actual identifiers out of the candidate Grype report and lists all of them as
products for one statement, so the assertion matches however Grype refers to the
image. The vulnerable package's PURL is likewise copied verbatim from the report.

Everything is derived from scans/candidate/candidate-grype.json, so the document
regenerates in step with the image: rebuild, rescan, re-run, and the digests and
PURL update themselves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

OPENVEX_CONTEXT = "https://openvex.dev/ns/v0.2.0"
AUTHOR = "Echo image maintainers"

# CVEs fixed by backport (source patched, version string unchanged). Each needs
# a VEX statement so the scanner stops reporting it. The version-bump CVEs do
# NOT belong here: their version string changes, so the scanner drops them on
# its own.
BACKPORT_FIXED = ["CVE-2026-15176"]


def load_report(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def image_products(report: dict) -> list[str]:
    """Every identifier Grype might use for the scanned image, as PURLs/refs."""
    target = report.get("source", {}).get("target", {}) or {}
    products: list[str] = []

    tags = target.get("tags") or ([target["userInput"]] if target.get("userInput") else [])
    name = tags[0].split(":")[0] if tags else "image"

    # OCI PURLs keyed by the two digests Grype records for a local image.
    for digest_key in ("manifestDigest", "imageID"):
        digest = target.get(digest_key)
        if digest:
            tag = tags[0].split(":")[-1] if tags and ":" in tags[0] else None
            qualifier = f"?tag={tag}" if tag else ""
            products.append(f"pkg:oci/{name}@{digest}{qualifier}")

    # Plain tag reference, for the Grype versions that match on user input.
    products.extend(tags)

    # De-duplicate, preserve order.
    seen: set[str] = set()
    ordered: list[str] = []
    for p in products:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def package_purl(report: dict, cve: str) -> str | None:
    for m in report.get("matches", []):
        if m.get("vulnerability", {}).get("id") == cve:
            purl = m.get("artifact", {}).get("purl")
            if purl:
                return purl
    return None


def build_document(report: dict, cves: list[str]) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    products = image_products(report)
    if not products:
        sys.exit("error: no image identifiers found in the Grype report")

    statements = []
    for cve in cves:
        purl = package_purl(report, cve)
        if purl is None:
            print(f"warning: {cve} not present in the report; skipping", file=sys.stderr)
            continue
        statements.append(
            {
                "vulnerability": {"name": cve},
                "timestamp": now,
                "products": [
                    {"@id": prod, "subcomponents": [{"@id": purl}]} for prod in products
                ],
                "status": "fixed",
                "status_notes": (
                    "Fixed by backporting the upstream patch for this CVE onto the "
                    "shipped source. The Debian package version is unchanged, so "
                    "version-based scanners still flag it; this statement records "
                    "that the vulnerable code path is patched in the binary."
                ),
            }
        )

    if not statements:
        sys.exit("error: none of the requested CVEs were found in the report")

    # Deterministic @id from the content, so regenerating an unchanged document
    # yields a stable identifier (openvex convention).
    digest = hashlib.sha256(
        json.dumps(statements, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "@context": OPENVEX_CONTEXT,
        "@id": f"https://openvex.dev/docs/echo/vex-{digest}",
        "author": AUTHOR,
        "role": "Document Creator",
        "timestamp": now,
        "version": 1,
        "statements": statements,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--grype-json",
        default="scans/candidate/candidate-grype.json",
        help="candidate Grype JSON report to read identifiers from",
    )
    ap.add_argument(
        "--output",
        default="vex/echo-nginx.openvex.json",
        help="where to write the OpenVEX document",
    )
    ap.add_argument(
        "--cve",
        action="append",
        help="override the backport-fixed CVE list (repeatable)",
    )
    args = ap.parse_args()

    report = load_report(args.grype_json)
    doc = build_document(report, args.cve or BACKPORT_FIXED)

    import os

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")

    print(f"wrote {args.output}")
    for st in doc["statements"]:
        print(f"  {st['vulnerability']['name']}: {st['status']} "
              f"({len(st['products'])} product identities)")


if __name__ == "__main__":
    main()
