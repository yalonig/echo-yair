#!/usr/bin/env bash
# Version-bump remediation, built from source. Rebuilds PCRE2 from the Debian
# source package (apt source + dpkg-buildpackage) with a local version suffix, so
# the bump is a package we compiled rather than one apt handed us. nginx links the
# result dynamically, so this clears the PCRE2 CVEs without touching nginx's flags.
set -euo pipefail

LOCAL_SUFFIX="${LOCAL_SUFFIX:-+echo1}"
MIN_VERSION="${MIN_VERSION:-10.42-1+deb12u1}"   # the CVE-fixed Debian version
OUT_DIR="${OUT_DIR:-/out}"
WORK="${WORK:-/tmp/pcre2-build}"

log() { printf '\n==> %s\n' "$*" >&2; }

log "1/6  Enable Debian source repositories (bookworm-slim ships none)"
if [ -f /etc/apt/sources.list.d/debian.sources ]; then
  sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources
elif [ -f /etc/apt/sources.list ]; then
  sed -i 's|^deb \(.*\)$|deb \1\ndeb-src \1|' /etc/apt/sources.list
fi
apt-get update

log "2/6  Install build tooling"
apt-get install -y --no-install-recommends \
  build-essential dpkg-dev devscripts ca-certificates

log "3/6  Fetch the PCRE2 source (apt source pcre2)"
mkdir -p "$WORK"; cd "$WORK"
apt-get source pcre2
srcdir="$(find . -maxdepth 1 -type d -name 'pcre2-*' | head -1)"
test -n "$srcdir" || { echo "ERROR: pcre2 source directory not found" >&2; exit 1; }
cd "$srcdir"

log "4/6  Verify the source is at least the fixed version, then bump it"
cur="$(dpkg-parsechangelog -S Version)"
dpkg --compare-versions "$cur" ge "$MIN_VERSION" \
  || { echo "ERROR: Debian pcre2 ${cur} is older than the fixed ${MIN_VERSION}" >&2; exit 1; }
new="${cur}${LOCAL_SUFFIX}"
DEBEMAIL="builds@echo.example" DEBFULLNAME="Echo Builds" \
  dch --newversion "$new" --distribution bookworm --force-distribution \
  "Rebuild from source as the version-bump remediation (Debian base: ${cur})."
log "    PCRE2 ${cur} -> ${new}"

log "5/6  Install build dependencies and build the package"
apt-get build-dep -y pcre2
DEB_BUILD_OPTIONS="parallel=$(nproc)" dpkg-buildpackage -us -uc -b

log "6/6  Collect the runtime library package that nginx links"
mkdir -p "$OUT_DIR"
cp "${WORK}"/libpcre2-8-0_*.deb "$OUT_DIR"/
ls -la "$OUT_DIR" >&2

# Drop the build tree in this same layer so the build image stays small.
cd /; rm -rf "$WORK"
