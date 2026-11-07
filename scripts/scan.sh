#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'Usage: %s <image> <output-dir> <report-prefix>\n' "$0" >&2
  exit 2
fi

image="$1"
out_dir="$2"
prefix="$3"
base="${out_dir}/${prefix}"

mkdir -p "$out_dir"
# Pull only if the image is not already present (the candidate image is built
# locally and has no registry to pull from).
docker image inspect "$image" >/dev/null 2>&1 || docker pull --quiet "$image" >/dev/null

printf 'Scanning %s with Trivy\n' "$image"
trivy image --scanners vuln --format json --output "${base}-trivy.json" "$image"
trivy convert --format table --output "${base}-trivy.txt" "${base}-trivy.json"

printf 'Scanning %s with Grype\n' "$image"
grype "$image" --output "table=${base}-grype.txt" --output "json=${base}-grype.json"

{
  printf 'image: %s\n' "$image"
  printf 'scanned_at: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '\n# trivy\n'
  trivy --version
  printf '\n# grype\n'
  grype version
  printf '\n# grype database\n'
  grype db status
} >"${base}-meta.txt"

# Full package inventory, so the diff can tell "fixed by a newer version" from
# "package not shipped" (component removal).
docker run --rm --entrypoint dpkg-query "$image" -W -f='${Package}\n' | sort -u >"${base}-packages.txt"

python3 tools/triage.py \
  --trivy "${base}-trivy.json" \
  --grype "${base}-grype.json" \
  --output "${base}-triage.csv"
