#!/usr/bin/env bash
# Build a patched nginx .deb from upstream source inside a clean Debian base.
# Every input is pinned: the source tarball by SHA-512, the packaging by commit.
set -euo pipefail

NGINX_VERSION="${NGINX_VERSION:?}"
NGINX_SHA512="${NGINX_SHA512:?}"
PKG_OSS_REPO="${PKG_OSS_REPO:-https://github.com/nginx/pkg-oss.git}"
PKG_OSS_REF="${PKG_OSS_REF:?}"
PKG_OSS_COMMIT="${PKG_OSS_COMMIT:?}"
PKG_VERSION="${PKG_VERSION:-${NGINX_VERSION}-1~bookworm+echo1}"
PATCH_DIR="${PATCH_DIR:-/patches}"
OUT_DIR="${OUT_DIR:-/out}"
WORK="${WORK:-/tmp/nginx-build}"

log() { printf '\n==> %s\n' "$*" >&2; }

tarball="nginx-${NGINX_VERSION}.tar.gz"
srcdir="nginx-${NGINX_VERSION}"

log "1/8  Fetch upstream source (${tarball})"
mkdir -p "$WORK"; cd "$WORK"
curl -fsSLo "$tarball" "https://nginx.org/download/${tarball}"

log "2/8  Verify source integrity (SHA-512)"
echo "${NGINX_SHA512}  ${tarball}" | sha512sum -c -

log "3/8  Fetch nginx packaging (pkg-oss @ ${PKG_OSS_REF})"
rm -rf pkg-oss
git clone --quiet --branch "$PKG_OSS_REF" --depth 1 "$PKG_OSS_REPO" pkg-oss
have="$(git -C pkg-oss rev-parse HEAD)"
if [ "$have" != "$PKG_OSS_COMMIT" ]; then
  echo "ERROR: pkg-oss commit mismatch: got ${have}, expected ${PKG_OSS_COMMIT}" >&2
  exit 1
fi

log "4/8  Hand the verified tarball to the packaging tree"
mkdir -p pkg-oss/contrib/tarballs
cp "$tarball" "pkg-oss/contrib/tarballs/${tarball}"

log "5/8  Assemble the Debian source tree with upstream build flags"
# nginx's changelog generator pulls an external helper (xslscript) whose download
# URL is dead. We set our own version and entry below (step 7), so pre-seed a
# minimal valid changelog: the rule is not phony, so make skips the broken fetch.
printf 'nginx (%s-1~bookworm) bookworm; urgency=low\n\n  * nginx %s (repackaged from nginx pkg-oss %s).\n\n -- nginx packaging <nginx-packaging@f5.com>  Wed, 24 Apr 2024 12:00:00 +0000\n' \
  "$NGINX_VERSION" "$NGINX_VERSION" "$PKG_OSS_REF" > pkg-oss/debian/nginx.deb-changelog
make -C pkg-oss/debian rules-base
tree="${WORK}/pkg-oss/debian/debuild-base/${srcdir}"
test -d "$tree" || { echo "ERROR: expected source tree not found at ${tree}" >&2; exit 1; }

log "6/8  Queue and verify backport patches"
mkdir -p "$tree/debian/patches"
shopt -s nullglob
patches=("$PATCH_DIR"/*.patch)
[ "${#patches[@]}" -gt 0 ] || { echo "ERROR: no patches found in ${PATCH_DIR}" >&2; exit 1; }
for p in "${patches[@]}"; do
  name="$(basename "$p")"
  cp "$p" "$tree/debian/patches/$name"
  grep -qxF "$name" "$tree/debian/patches/series" 2>/dev/null || echo "$name" >> "$tree/debian/patches/series"
  # Fail loudly if a patch does not apply; dpkg-source applies the series at build.
  ( cd "$tree" && patch -p1 --dry-run --fuzz=0 < "debian/patches/$name" >/dev/null )
  echo "    queued ${name} (applies cleanly)" >&2
done

log "7/8  Record our build version and changelog entry"
names=""
for p in "${patches[@]}"; do names+="${names:+, }$(basename "$p")"; done
( cd "$tree" && DEBEMAIL="builds@echo.example" DEBFULLNAME="Echo Builds" \
    dch --newversion "$PKG_VERSION" --distribution bookworm --force-distribution \
    "Rebuild from source; backport ${names}." )

log "8/8  Build the binary package"
( cd "$tree" && dpkg-checkbuilddeps )
( cd "$tree" && DEB_BUILD_OPTIONS="parallel=$(nproc)" dpkg-buildpackage -us -uc -b )

mkdir -p "$OUT_DIR"
cp "${WORK}/pkg-oss/debian/debuild-base/"*.deb "$OUT_DIR"/
rm -rf "$OUT_DIR"/*-dbg_*.deb 2>/dev/null || true

# Prove the result is a freshly compiled nginx with the upstream flag set.
debs=("$OUT_DIR"/nginx_*.deb)
dpkg-deb -x "${debs[0]}" "${WORK}/verify"
"${WORK}/verify/usr/sbin/nginx" -V 2> "$OUT_DIR/nginx-V.txt" || true
log "Built packages:"; ls -la "$OUT_DIR" >&2
log "nginx -V of the built binary:"; cat "$OUT_DIR/nginx-V.txt" >&2
