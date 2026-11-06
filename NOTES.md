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
