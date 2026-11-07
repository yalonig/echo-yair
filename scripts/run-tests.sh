#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=/dev/null
source versions.env

candidate="echo-nginx:${NGINX_VERSION}"
# Boot the same pinned upstream the scans use (tag@digest), not a moving tag.
upstream="${UPSTREAM_IMAGE}"
[ -n "${UPSTREAM_DIGEST:-}" ] && upstream="${UPSTREAM_IMAGE}@${UPSTREAM_DIGEST}"
if ! docker image inspect "$candidate" >/dev/null 2>&1; then
  echo "Image $candidate not found. Run 'make image' first." >&2
  exit 1
fi
if ! docker image inspect "$upstream" >/dev/null 2>&1; then
  docker pull "$upstream" >/dev/null
fi

run_pytest() {
  env UPSTREAM_IMAGE="$upstream" CANDIDATE_IMAGE="$candidate" \
      "$@" -v --durations=5 test/
}

# Prefer an isolated venv on a native filesystem (not the Windows mount).
venv="${TMPDIR:-/tmp}/echo-nginx-venv"
if python3 -m venv "$venv" >/dev/null 2>&1 \
   && "$venv/bin/pip" install -q -r test/requirements.txt >/dev/null 2>&1; then
  run_pytest "$venv/bin/pytest"
  exit $?
fi

# Fallback: the venv module is unavailable (install python3-venv for isolation).
echo "venv unavailable; installing test deps into the current environment." >&2
if python3 -m pip install -q --break-system-packages -r test/requirements.txt 2>/dev/null \
   || python3 -m pip install -q -r test/requirements.txt; then
  run_pytest python3 -m pytest
else
  echo "Could not install test dependencies. Install python3-venv and python3-pip:" >&2
  echo "  sudo apt-get install -y python3-venv python3-pip" >&2
  exit 1
fi
