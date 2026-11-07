#!/usr/bin/env bash
set -euo pipefail

# Regenerate the OpenVEX document from the latest candidate scan, then prove it
# works: re-run Grype against the candidate image with --vex and confirm the
# backport-fixed CVE moves from "reported" to "suppressed by VEX".
#
# Requires: make scan-candidate has run (so scans/candidate/candidate-grype.json
# exists) and the candidate image is built.

source versions.env

image="echo-nginx:${NGINX_VERSION}"
vex_doc="vex/echo-nginx.openvex.json"
report="scans/candidate/candidate-grype.json"
vex_json="scans/candidate/vex-grype.json"
vex_txt="scans/candidate/vex-grype.txt"

if [[ ! -f "$report" ]]; then
  printf 'error: %s not found; run `make scan-candidate` first\n' "$report" >&2
  exit 1
fi

printf 'Generating %s from %s\n' "$vex_doc" "$report"
python3 tools/make_vex.py --grype-json "$report" --output "$vex_doc"

printf '\nRe-scanning %s with the VEX document applied\n' "$image"
grype "$image" --vex "$vex_doc" --show-suppressed \
  --output "table=${vex_txt}" --output "json=${vex_json}"

printf '\nChecking that every backport-fixed CVE is now suppressed\n'
python3 - "$vex_doc" "$vex_json" <<'PY'
import json, sys

vex_doc, vex_json = sys.argv[1], sys.argv[2]

claimed = {s["vulnerability"]["name"] for s in json.load(open(vex_doc))["statements"]}
scan = json.load(open(vex_json))

active = {m["vulnerability"]["id"] for m in scan.get("matches", [])}
def _by_vex(m):
    return any(r.get("namespace") == "vex" for r in m.get("appliedIgnoreRules", []))
ignored = {m["vulnerability"]["id"] for m in scan.get("ignoredMatches", []) if _by_vex(m)}

ok = True
for cve in sorted(claimed):
    if cve in active:
        print(f"  FAIL  {cve}: still reported as an active match")
        ok = False
    elif cve in ignored:
        print(f"  ok    {cve}: suppressed by VEX")
    else:
        print(f"  FAIL  {cve}: not in the scan at all (PURL drift?)")
        ok = False

if not ok:
    print("\nVEX did not suppress every claimed CVE. The product identifiers in")
    print("the document probably do not match how Grype refers to this image;")
    print("inspect scans/candidate/vex-grype.txt and the image products in the doc.")
    sys.exit(1)

print(f"\nAll {len(claimed)} backport-fixed CVE(s) suppressed by VEX.")
PY

printf '\nSuppressed-match table written to %s\n' "$vex_txt"
