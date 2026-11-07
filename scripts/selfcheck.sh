#!/usr/bin/env bash
set -euo pipefail

# Prove the test suite can fail. A suite that passes against our image means
# nothing unless it FAILS against images that are wrong, so run it twice:
#
#  1. upstream vs ITSELF: identical images, so every parity test must pass, and
#     the CVE-fix test must fail (upstream is not patched). Proves the CVE test
#     detects the fix, and that parity tests don't flag correct matches.
#  2. upstream vs a DIFFERENT nginx release: the parity suites must fail.
#     Proves they detect a server that is not a drop-in.
#
# Requires `make test` to have run once (it creates the test venv).

source versions.env
other="${SELFCHECK_OTHER_IMAGE:-nginx:1.27-bookworm}"
upstream="${UPSTREAM_IMAGE}"   # the same pinned upstream the scans and tests use
[ -n "${UPSTREAM_DIGEST:-}" ] && upstream="${UPSTREAM_IMAGE}@${UPSTREAM_DIGEST}"
pytest="${TMPDIR:-/tmp}/echo-nginx-venv/bin/pytest"
[ -x "$pytest" ] || { echo "Run 'make test' first (it creates the test venv)." >&2; exit 1; }

failed_tests() {  # <candidate image> -> sorted failing test ids
  # The self-check must not be vacuous either: pytest exit 0 (all passed) or 1
  # (some failed) means the suite really ran. Anything else (collection error,
  # no tests collected, a broken working directory) aborts instead of being
  # misread as "nothing failed".
  local out rc=0
  out="$(UPSTREAM_IMAGE="$upstream" CANDIDATE_IMAGE="$1" \
         "$pytest" -q -rf -p no:cacheprovider test/ 2>&1)" || rc=$?
  if [ "$rc" -gt 1 ]; then
    printf 'ERROR: the test suite did not run against %s (pytest exit %s):\n' "$1" "$rc" >&2
    tail -n 15 <<<"$out" >&2
    exit 2
  fi
  sed -n 's/^FAILED \([^ ]*\).*/\1/p' <<<"$out" | sort
}

ok=1

printf '1/2  upstream vs itself (%s)\n' "$upstream"
got="$(failed_tests "$upstream")" || exit $?
want="test/compat_test.py::test_cve_2026_15176_is_fixed"
if [ "$got" = "$want" ]; then
  echo "     ok   only the CVE-fix test failed: it detects the patch, and parity holds for identical images"
else
  echo "     FAIL expected exactly: $want"; echo "          got: ${got:-<nothing failed>}"; ok=0
fi

printf '2/2  upstream vs a different nginx (%s)\n' "$other"
docker image inspect "$other" >/dev/null 2>&1 || docker pull --quiet "$other" >/dev/null
got="$(failed_tests "$other")" || exit $?
# Only demand failures that MUST happen against another release: every response
# and error page names the version (Server: nginx/1.27.x), and 1.27 lacks the CVE
# fix, and its NGINX_VERSION differs. (Its packaged config could legitimately equal
# ours, so nginx -T is not required.)
for t in compat_test.py::test_http_parity compat_test.py::test_raw_parity \
         default_test.py::test_default_config_parity contract_test.py::test_environment_matches \
         compat_test.py::test_cve_2026_15176_is_fixed; do
  n="$(grep -c "$t" <<<"$got" || true)"
  if [ "$n" -gt 0 ]; then echo "     ok   $t: $n failing case(s)"
  else echo "     FAIL $t did not fail against a different nginx"; ok=0; fi
done
echo "     ($(grep -c . <<<"$got" || true) failing tests in total)"

if [ "$ok" -eq 1 ]; then echo; echo "Self-check passed: the suite fails when it should."
else echo; echo "Self-check FAILED: some test cannot detect what it claims to." >&2; exit 1; fi
