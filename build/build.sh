#!/usr/bin/env bash
# Build the patched nginx .deb AND its four dynamic-module .debs (geoip,
# image-filter, njs, xslt) from upstream source inside a clean Debian base.
# Every input is pinned: tarballs by SHA-512 (or git commit), packaging by commit.
set -euo pipefail

NGINX_VERSION="${NGINX_VERSION:?}"
NGINX_SHA512="${NGINX_SHA512:?}"
NJS_VERSION="${NJS_VERSION:?}"
NJS_GITHUB_SHA512="${NJS_GITHUB_SHA512:?}"
PKG_OSS_REPO="${PKG_OSS_REPO:-https://github.com/nginx/pkg-oss.git}"
PKG_OSS_REF="${PKG_OSS_REF:?}"
PKG_OSS_COMMIT="${PKG_OSS_COMMIT:?}"
LOCAL_SUFFIX="${LOCAL_SUFFIX:-+echo1}"
PATCH_DIR="${PATCH_DIR:-/patches}"
OUT_DIR="${OUT_DIR:-/out}"
WORK="${WORK:-/tmp/nginx-build}"
MODULES=(geoip image-filter njs xslt)   # exactly the four the upstream image ships

CODENAME="$(lsb_release -cs)"
PKG_VERSION="${NGINX_VERSION}-1~${CODENAME}${LOCAL_SUFFIX}"
tarball="nginx-${NGINX_VERSION}.tar.gz"
srcdir="nginx-${NGINX_VERSION}"
PKGOSS="${WORK}/pkg-oss"

log() { printf '\n==> %s\n' "$*" >&2; }

shopt -s nullglob
patches=("$PATCH_DIR"/*.patch)
[ "${#patches[@]}" -gt 0 ] || { echo "ERROR: no patches found in ${PATCH_DIR}" >&2; exit 1; }
patch_names=""
for p in "${patches[@]}"; do patch_names+="${patch_names:+, }$(basename "$p")"; done

# Apply every backport to a source tree and prove it is applied. We do NOT rely
# on dpkg-source/quilt to apply a series at build time: in this setup that step
# did not run, shipping an unpatched binary. A reverse dry-run must succeed.
apply_patches() {
  local tree="$1"
  for p in "${patches[@]}"; do
    ( cd "$tree" && patch -p1 --fuzz=0 < "$p" )
    ( cd "$tree" && patch -R -p1 --fuzz=0 --dry-run < "$p" >/dev/null ) \
      || { echo "ERROR: $(basename "$p") did not apply to ${tree}" >&2; exit 1; }
    echo "    applied and verified $(basename "$p") in ${tree##*/debian/}" >&2
  done
}

# Stamp our version on a tree (traceable +echo1 suffix) and build its packages.
stamp_and_build() {
  local tree="$1" version="$2" msg="$3"
  ( cd "$tree" && DEBEMAIL="builds@echo.example" DEBFULLNAME="Echo Builds" \
      dch --newversion "$version" --distribution "$CODENAME" --force-distribution "$msg" )
  ( cd "$tree" && dpkg-checkbuilddeps )
  ( cd "$tree" && DEB_BUILD_OPTIONS="parallel=$(nproc)" dpkg-buildpackage -us -uc -b )
}

# nginx's changelog generator fetches an external helper (xslscript) from a dead
# URL. The changelog rules are not phony, so pre-seeding the file skips the fetch;
# dch then adds our real entry on top.
seed_changelog() {
  local file="$1" pkg="$2" version="$3"
  printf '%s (%s) %s; urgency=low\n\n  * %s from nginx pkg-oss %s.\n\n -- nginx packaging <nginx-packaging@f5.com>  Wed, 24 Apr 2024 12:00:00 +0000\n' \
    "$pkg" "$version" "$CODENAME" "$pkg" "$PKG_OSS_REF" > "$file"
}

log "1/10  Fetch upstream source (${tarball})"
mkdir -p "$WORK"; cd "$WORK"
curl -fsSLo "$tarball" "https://nginx.org/download/${tarball}"

log "2/10  Verify source integrity (SHA-512)"
echo "${NGINX_SHA512}  ${tarball}" | sha512sum -c -

log "3/10  Fetch nginx packaging (pkg-oss @ ${PKG_OSS_COMMIT})"
rm -rf "$PKGOSS"
# Fetch the exact pinned commit (not a moving branch or tag), shallow.
git init --quiet "$PKGOSS"
git -C "$PKGOSS" remote add origin "$PKG_OSS_REPO"
git -C "$PKGOSS" fetch --quiet --depth 1 origin "$PKG_OSS_COMMIT"
git -C "$PKGOSS" checkout --quiet FETCH_HEAD
have="$(git -C "$PKGOSS" rev-parse HEAD)"
[ "$have" = "$PKG_OSS_COMMIT" ] \
  || { echo "ERROR: pkg-oss commit mismatch: got ${have}, expected ${PKG_OSS_COMMIT}" >&2; exit 1; }
pkgoss_njs="$(sed -n 's/^NJS_VERSION := //p' "$PKGOSS/contrib/src/njs/version")"
[ "$pkgoss_njs" = "$NJS_VERSION" ] \
  || { echo "ERROR: pkg-oss pins njs ${pkgoss_njs}, versions.env pins ${NJS_VERSION}" >&2; exit 1; }

log "4/10  Hand the verified tarball to the packaging tree"
mkdir -p "$PKGOSS/contrib/tarballs"
cp "$tarball" "$PKGOSS/contrib/tarballs/${tarball}"

log "5/10  Assemble the nginx source tree with upstream build flags"
seed_changelog "$PKGOSS/debian/nginx.deb-changelog" nginx "${NGINX_VERSION}-1~${CODENAME}"
make -C "$PKGOSS/debian" rules-base
tree="$PKGOSS/debian/debuild-base/${srcdir}"
test -d "$tree" || { echo "ERROR: expected source tree not found at ${tree}" >&2; exit 1; }

log "6/10  Apply and verify backport patches (nginx)"
apply_patches "$tree"

log "7/10  Build the nginx package (${PKG_VERSION})"
stamp_and_build "$tree" "$PKG_VERSION" "Rebuild from source; backport ${patch_names}."
mkdir -p "$OUT_DIR"
cp "$PKGOSS/debian/debuild-base/"*.deb "$OUT_DIR"/

log "8/10  Fetch njs ${NJS_VERSION} source (verified) for the njs module"
# pkg-oss downloads njs from nginx's contrib mirror and checks it against its own
# pinned SHA-512. If that mirror is unavailable, fall back to njs's official
# GitHub release tarball, checked against the SHA-512 pinned in versions.env.
contrib="$PKGOSS/contrib"
njs_tgz="njs-${NJS_VERSION}.tar.gz"
if make -C "$contrib" .sum-njs; then
  echo "    njs: nginx contrib mirror, verified with pkg-oss's checksum" >&2
else
  echo "    njs: contrib mirror unavailable; using the GitHub release (pinned SHA-512)" >&2
  rm -f "$contrib/tarballs/${njs_tgz}" "$contrib/.sum-njs"
  curl -fsSLo "$contrib/tarballs/${njs_tgz}" \
    "https://github.com/nginx/njs/archive/refs/tags/${NJS_VERSION}.tar.gz"
  ( cd "$contrib/tarballs" && echo "${NJS_GITHUB_SHA512}  ${njs_tgz}" | sha512sum -c - )
  echo "${NJS_GITHUB_SHA512}  ${njs_tgz}" > "$contrib/src/njs/SHA512SUMS"
  make -C "$contrib" .sum-njs
fi

log "9/10  Build the dynamic-module packages: ${MODULES[*]}"
for m in "${MODULES[@]}"; do
  # Release number as pkg-oss defines it (njs is release 3 at the pinned commit).
  mrel="$(sed -n "s/^MODULE_RELEASE_${m//-/_}=[[:space:]]*//p" "$PKGOSS/debian/Makefile.module-${m}")"
  [ -n "$mrel" ] || { echo "ERROR: no MODULE_RELEASE for ${m} in pkg-oss" >&2; exit 1; }
  if [ "$m" = njs ]; then mver="${NGINX_VERSION}+${NJS_VERSION}-${mrel}~${CODENAME}"
  else mver="${NGINX_VERSION}-${mrel}~${CODENAME}"; fi
  log "      nginx-module-${m} (${mver}${LOCAL_SUFFIX})"
  seed_changelog "$PKGOSS/debian/nginx-module-${m}.deb-changelog" "nginx-module-${m}" "$mver"
  make -C "$PKGOSS/debian" "rules-module-${m}"
  mtree="$PKGOSS/debian/debuild-module-${m}/${srcdir}"
  test -d "$mtree" || { echo "ERROR: module tree not found at ${mtree}" >&2; exit 1; }
  # Same patched source as the nginx binary, so every tree we compile carries it.
  apply_patches "$mtree"
  stamp_and_build "$mtree" "${mver}${LOCAL_SUFFIX}" \
    "Build nginx-module-${m} from source alongside the patched nginx (${patch_names})."
  cp "$PKGOSS/debian/debuild-module-${m}/"*.deb "$OUT_DIR"/
done
rm -f "$OUT_DIR"/*-dbg_*.deb

log "10/10  Verify the outputs"
debs=("$OUT_DIR"/nginx_*.deb)
dpkg-deb -x "${debs[0]}" "${WORK}/verify"
"${WORK}/verify/usr/sbin/nginx" -V 2> "$OUT_DIR/nginx-V.txt" || true
for m in "${MODULES[@]}"; do
  mdeb=("$OUT_DIR"/nginx-module-"${m}"_*.deb)
  [ "${#mdeb[@]}" -eq 1 ] || { echo "ERROR: expected one nginx-module-${m} package" >&2; exit 1; }
  echo "    nginx-module-${m}: $(dpkg-deb -c "${mdeb[0]}" | grep -o 'ngx_[a-z_]*module\.so' | sort -u | tr '\n' ' ')" >&2
done
log "Built packages:"; ls -la "$OUT_DIR" >&2
log "nginx -V of the built binary:"; cat "$OUT_DIR/nginx-V.txt" >&2

# Drop the build tree (sources, both nginx builds, all module objects) in this same
# layer, so the throwaway build image does not keep gigabytes on disk.
cd /; rm -rf "$WORK"
