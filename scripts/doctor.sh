#!/usr/bin/env bash
set -euo pipefail

failed=0

check_tool() {
  local tool="$1"
  if command -v "$tool" >/dev/null 2>&1; then
    printf 'OK       %s\n' "$tool"
  else
    printf 'MISSING  %s\n' "$tool"
    failed=1
  fi
}

for tool in git make python3 docker trivy grype; do
  check_tool "$tool"
done

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    printf 'OK       docker daemon\n'
  else
    printf 'MISSING  docker daemon (start Docker Desktop)\n'
    failed=1
  fi
fi

if grep -q $'\r' Makefile versions.env scripts/*.sh; then
  printf 'BAD      CRLF line endings found; re-clone after adding .gitattributes\n'
  failed=1
else
  printf 'OK       LF line endings\n'
fi

exit "$failed"
