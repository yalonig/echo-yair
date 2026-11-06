# Engineering notes

Log surprises, failed attempts, and decisions here while working.

## Toolchain

- Development environment: Windows with Ubuntu on WSL 2 and Docker Desktop.
- Trivy 0.76.2 and Grype 0.121.2.

## `set -e` does not protect command substitution

The first version of `scripts/pin-images.sh` pulled images inside a function
called from `$(...)`. Bash ignores `set -e` there, so a failed `docker pull` did
not stop the script. The next command then reported `No such image`, which hid
the real failure.

Fix: pull images before any command substitution, so a failed pull stops the
script straight away. I tested this with a simulated pull failure, and the script
exited without changing `versions.env`.

## nginx's packaging tries to download a tool from a dead URL

Building the `.deb` through nginx's own packaging (`pkg-oss`) failed at the
source-tree assembly step:

    curl: (22) The requested URL returned error: 404
    xslscript-01dc9ba12e1b.tar.gz: FAILED

`pkg-oss` generates the Debian changelog from XML, and that step first downloads
a helper tool (`xslscript`) to compile the XSLT. The download URL is no longer
hosted, so the build aborted. Nothing to do with our patch or nginx itself.

Fix: we set our own package version and changelog entry anyway (`dch`), so the
generated changelog is not needed. The changelog rule is not phony, so writing a
minimal valid `debian/nginx.deb-changelog` before running the build satisfies the
rule and skips the broken download. See `build/build.sh` step 5.

Takeaway: pinning the upstream packaging to a fixed revision makes the build
reproducible, but it does not protect against an external URL that rots. A fully
hermetic build would vendor that helper too.

## Keeping the dynamic modules without rebuilding them

The upstream image ships four dynamic modules (geoip, image-filter, njs, xslt)
that the default config does not load. A from-scratch image omits them, which is
allowed for extras but is a visible gap for a "drop-in".

Rather than rebuild all four from source (njs alone is a separate project with
its own tarball), we copy the prebuilt `.so` files from the upstream image.
nginx builds modules with `--with-compat`, so a stock module loads into any
same-version nginx; ours is the same 1.25.5, also `--with-compat`. Two snags:

1. First load failed with `... is not binary compatible` only if compat is
   missing — ours passed that check, confirming the ABI assumption.
2. Then it failed with `libxml2.so.2: cannot open shared object file`. The .so
   files link extra libraries (njs/xslt -> libxml2, xslt -> libxslt,
   image-filter -> libgd, geoip -> libgeoip) that the upstream image got via its
   module packages. Copying only the .so files left those out, so we install the
   runtime libraries explicitly in the Containerfile.

Verified: `nginx -t` loads all four modules in the final image.

## The backport compiled but was not in the binary

The compatibility suite's CVE test caught this: the drop-in image returned 200
on the alias+rewrite trigger, exactly like the unpatched upstream, instead of the
patched build's 500. The parity tests all passed, so the image was a faithful
drop-in -- of the *unpatched* nginx.

Cause: the build added the patch to `debian/patches/series` and trusted
`dpkg-buildpackage` (source format "3.0 (quilt)") to apply the series at build
time. In this setup that application did not happen, so nginx compiled from the
pristine source.

Fix: apply the patch directly to the source tree that `debian/rules` compiles
(it copies `$(CURDIR)/src` into the build dir), then verify with a reverse
dry-run that it is really applied before building. The behavioural CVE test now
passes.

Lesson: "the patch applies cleanly" is not "the patch is in the binary." Only a
test that exercises the fixed behaviour proves the backport shipped.
