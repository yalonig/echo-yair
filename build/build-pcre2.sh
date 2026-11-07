#!/usr/bin/env bash
# Version-bump remediation, built from source. Rebuilds PCRE2 from the Debian
# source package (apt source + dpkg-buildpackage) with a local version suffix, so
# the bump is a package we compiled rather than one apt handed us. nginx links the
# result dynamically, so this clears the PCRE2 CVEs without touching nginx's flags.
set -euo pipefail

LOCAL_SUFFIX="${LOCAL_SUFFIX:-+echo1}"
MIN_VERSION="${MIN_VERSION:-10.42-1+deb12u1}"   # the CVE-fixed Debian version
PCRE2_VERSION="${PCRE2_VERSION:?}"               # exact source version (versions.env)
PCRE2_SNAPSHOT="${PCRE2_SNAPSHOT:?}"             # snapshot.debian.org fallback timestamp
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

log "3/6  Fetch the PCRE2 source (pcre2=${PCRE2_VERSION})"
mkdir -p "$WORK"; cd "$WORK"
# Pinned to an exact version. Debian drops old versions from the live archive
# when a newer update lands, so if the pin is gone (or PCRE2_FROM_SNAPSHOT is
# set, to exercise this path), fetch it from snapshot.debian.org, Debian's
# immutable archive. apt verifies the snapshot's signed Release files either way.
if [ -z "${PCRE2_FROM_SNAPSHOT:-}" ] && apt-get source "pcre2=${PCRE2_VERSION}"; then
  echo "    source: live Debian archive" >&2
else
  echo "    source: snapshot.debian.org @ ${PCRE2_SNAPSHOT}" >&2
  rm -rf pcre2-* pcre2_*
  snap="https://snapshot.debian.org/archive"
  cat > /etc/apt/sources.list.d/snapshot.list <<SRC
deb-src [check-valid-until=no] ${snap}/debian/${PCRE2_SNAPSHOT}/ bookworm main
deb-src [check-valid-until=no] ${snap}/debian/${PCRE2_SNAPSHOT}/ bookworm-updates main
deb-src [check-valid-until=no] ${snap}/debian-security/${PCRE2_SNAPSHOT}/ bookworm-security main
SRC
  apt-get update
  apt-get source "pcre2=${PCRE2_VERSION}"
fi
srcdir="$(find . -maxdepth 1 -type d -name 'pcre2-*' | head -1)"
test -n "$srcdir" || { echo "ERROR: pcre2 source directory not found" >&2; exit 1; }
cd "$srcdir"

log "4/6  Verify the source is at least the fixed version, then bump it"
cur="$(dpkg-parsechangelog -S Version)"
[ "$cur" = "$PCRE2_VERSION" ] \
  || { echo "ERROR: fetched pcre2 ${cur}, pinned ${PCRE2_VERSION}" >&2; exit 1; }
dpkg --compare-versions "$cur" ge "$MIN_VERSION" \
  || { echo "ERROR: Debian pcre2 ${cur} is older than the fixed ${MIN_VERSION}" >&2; exit 1; }
new="${cur}${LOCAL_SUFFIX}"
DEBEMAIL="builds@echo.example" DEBFULLNAME="Echo Builds" \
  dch --newversion "$new" --distribution bookworm --force-distribution \
  "Rebuild from source as the version-bump remediation (Debian base: ${cur})."
log "    PCRE2 ${cur} -> ${new}"

log "5/6  Install build dependencies and build the package"
# Build-Depends from the fetched source's own debian/control, not today's index.
apt-get build-dep -y ./
DEB_BUILD_OPTIONS="parallel=$(nproc)" dpkg-buildpackage -us -uc -b

log "6/6  Collect the runtime library package that nginx links"
mkdir -p "$OUT_DIR"
cp "${WORK}"/libpcre2-8-0_*.deb "$OUT_DIR"/
ls -la "$OUT_DIR" >&2

# Drop the build tree in this same layer so the build image stays small.
cd /; rm -rf "$WORK"
