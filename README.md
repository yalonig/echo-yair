# echo-nginx — a patched, drop-in rebuild of `nginx:1.25-bookworm`

A from-source rebuild of the official `nginx:1.25-bookworm` image that removes
known vulnerabilities using two different remediation techniques, while staying a
true drop-in replacement. The whole project reproduces from a clean checkout with
one command.

```bash
make all      # preflight, build 6 packages + the image, test, scan both images, diff, VEX
```

- **nginx and its four dynamic modules** (geoip, image-filter, njs, xslt) are
  compiled from upstream source with nginx's own packaging — nothing is repackaged
  from apt or copied out of the upstream image.
- **CVE-2026-15176** (a buffer overflow in nginx itself) is fixed by **backporting**
  the upstream patch. The package version can't change, so a VEX document tells
  scanners it's fixed.
- **PCRE2** is fixed by a **version bump**: rebuilt from Debian's patched source as
  our own package, clearing 7 CVEs.
- The image ships **every package the original does**, boots through the original
  entrypoint with the same user, ports and signal, and passes an automated parity
  suite against the original. The pipeline fails if any upstream package goes missing.

---

## Prerequisites

Linux (or WSL2 on Windows) with `docker`, `make`, `python3` (3.10+), `git`, `openssl`,
and the two scanners `trivy` and `grype`. The full pipeline needs roughly **10 GB of
free disk** (on WSL, on the Windows drive that holds Docker's virtual disk) and
**4 GB+ of RAM** for the scanners. `make doctor` checks all of this and `make all`
runs it first, so a low-disk machine gets a clear error instead of a crash mid-build.

## Quick start

```bash
make all            # doctor -> pcre2 -> deb -> image -> test -> scans -> vex
make selfcheck      # prove the tests can fail
```

`versions.env` already pins every input. Don't run `make pin` to set up: it
re-resolves the image tags and **overwrites** those pins with whatever the tags point
to today. Use it only when you deliberately want to move to newer base images.

Individual stages:

| Command | What it does |
|---|---|
| `make doctor` | Check tools (incl. Python 3.10+), line endings, disk and memory. |
| `make pcre2` | Rebuild the version-bumped PCRE2 `.deb` from Debian source. |
| `make deb` | Compile nginx + its 4 module `.deb`s from source in a clean `debian:bookworm-slim`. |
| `make image` | Build the drop-in image `echo-nginx:1.25.5` from those `.deb`s. |
| `make test` | Boot both images and assert identical responses + prove the CVE fix. |
| `make selfcheck` | Prove the tests can fail: run them against images that must fail them. |
| `make scan-baseline` | Scan the original image (Trivy + Grype) and record its package list. |
| `make scan-candidate` | Scan the rebuilt image and diff it; **fails if an upstream package is missing**. |
| `make vex` | Generate the OpenVEX document and prove it suppresses the backport CVE. |

Build outputs (`.deb`s, images, raw scan JSON) are intentionally **not** committed —
`make` regenerates them. The readable scan reports, package lists and the diff are
committed as evidence under `scans/`.

---

## The two remediation techniques

The brief asks for at least two *different* techniques and says removing
components doesn't count. Nothing is removed here — and `make scan-candidate`
enforces that (see *Results*).

### 1. Backport — CVE-2026-15176 (nginx)

A buffer overflow in `ngx_http_map_uri_to_path()`: in a `location` that uses
`alias` together with `rewrite`, the rewritten URI can become shorter than the
location prefix, and nginx writes past the end of the path buffer. Unauthenticated.

- **Why backport:** the fix first shipped in nginx 1.31.7 / 1.30.6, but we ship a
  1.25.x package to stay a drop-in. So we take the upstream one-line fix
  ([`f8a23425`](https://github.com/nginx/nginx/commit/f8a23425bd6840c4c36b4264edf576ba3646156f))
  and apply it to 1.25.5. The patch, with DEP-3 provenance, is in
  `build/patches/CVE-2026-15176.patch`.
- **The version does not change** (`1.25.5`), so scanners keep reporting it even
  though the code is fixed. That is the case VEX exists for (see *Scanning*).
- **Proof:** `test/compat_test.py::test_cve_2026_15176_is_fixed` sends the exact
  trigger request to both images. The patched build refuses the path mapping — it
  logs `"alias" cannot be used in location "/foo/" where URI was rewritten` and
  returns an empty body — while the original maps the path and returns it. A second
  test proves the fix is surgical: a plain, non-rewritten `alias` still works.

### 2. Version bump — PCRE2, rebuilt from source

nginx links PCRE2 for every regex in a config. The original ships `10.42-1`; Debian
fixed seven CVEs in `10.42-1+deb12u1`/`+deb12u2`.

| Library | Original | Rebuilt | Effect |
|---|---|---|---|
| `libpcre2-8-0` | `10.42-1` | `10.42-1+deb12u2+echo1` | clears 7 CVEs (incl. an arbitrary-code-execution OOB write) |

`build/build-pcre2.sh` (run via `make pcre2`) enables Debian source repos, fetches
the exact pinned source `pcre2=10.42-1+deb12u2`, bumps the version with a `+echo1`
suffix, and `dpkg-buildpackage` produces our own `libpcre2-8-0` `.deb`. Debian drops
old versions from its live archive when newer updates land, so if the pinned version
has gone, the build fetches it from snapshot.debian.org — Debian's immutable archive —
at a pinned timestamp, and the build stays reproducible. nginx links it
dynamically, so no nginx build flags change. Because the version string changes,
scanners see this fix on their own — no VEX needed.

**Not claimed as remediation — the base refresh.** Rebuilding on the current
`debian:bookworm-slim` also brings newer versions of other libraries (OpenSSL
`3.0.11` → `3.0.22`, curl, expat, …). That's a real benefit of rebuilding, but it
is apt's work, not ours, so it is reported separately and not counted. (TRIAGE.md
explains why OpenSSL wasn't chosen as a deliberate target.)

A **build gate** in the `Containerfile` fails the image build unless nginx, all four
modules and PCRE2 are our own `+echo1` packages — so an upstream or distro binary
can never silently stand in for them — and unless PCRE2 and OpenSSL are at or above
their CVE-fixed versions.

---

## Results

Scanned with Trivy 0.76.2 and Grype 0.121.2 using **the same vulnerability database
for both images** (recorded in `scans/*/…-meta.txt`), so the diff is fair. `make all`
rescans both images, so a reviewer's diff always uses one database too. Full
reports are in `scans/`; the diff is `scans/candidate/diff.md`. Severity counts can
shift as the databases re-rate CVEs: a clean-clone run on Nov 7 with a newer Grype
database gave identical totals (846 → 465, 381 fixed) with a few CVEs re-rated
(baseline Critical 56 → 60).

| | Baseline (original) | Candidate (rebuilt) |
|---|---|---|
| Total findings | 846 | 465 |
| Critical | 56 | 25 |
| High | 290 | 128 |

**381 findings fixed** (31 Critical, 162 High). Being exact about *why*:

- **7 are our version bump** (PCRE2).
- **The rest are the base refresh** — packages still shipped, at newer versions
  from current bookworm. The biggest groups are `openssl` (96), `expat` (33),
  `curl` (28), `krb5` (28), `gnutls28` (21) and `libxml2` (21).
- **None came from dropping a component.** Each scan records the image's full
  package list, and `make scan-candidate` uses both lists to split every
  disappeared finding into "fixed (newer version)" vs "package not shipped" —
  failing the run if any upstream package is missing. Verified: the two images
  have **identical package sets** (149 packages each) — nothing missing, nothing
  extra.
- **The backport is *not* in the fixed count — by design.** The scanner still
  reports CVE-2026-15176 because the version string didn't change. With the VEX
  document applied, Grype suppresses it (Grype's own count goes from 421 to 420
  matches), leaving **464** of the merged findings active.

### Per-CVE remediation

| CVE | Severity | Fix method | Evidence |
|---|---|---|---|
| CVE-2026-15176 | Critical (Grype 9.2; medium per nginx.org) | backport | [patch](build/patches/CVE-2026-15176.patch) · [behaviour test](test/compat_test.py) · [VEX](vex/echo-nginx.openvex.json) · [upstream fix](https://github.com/nginx/nginx/commit/f8a23425bd6840c4c36b4264edf576ba3646156f) |
| CVE-2026-103111 | High | bump — PCRE2 (from source) | [build script](build/build-pcre2.sh) · [scan diff](scans/candidate/diff.md) |
| CVE-2026-86145 | High | bump — PCRE2 | [scan diff](scans/candidate/diff.md) |
| CVE-2026-89157 | High | bump — PCRE2 | [scan diff](scans/candidate/diff.md) |
| CVE-2026-89161 | High | bump — PCRE2 | [scan diff](scans/candidate/diff.md) |
| CVE-2026-89156 | Medium | bump — PCRE2 | [scan diff](scans/candidate/diff.md) |
| CVE-2026-89158 | Medium | bump — PCRE2 | [scan diff](scans/candidate/diff.md) |
| CVE-2026-89160 | Medium | bump — PCRE2 | [scan diff](scans/candidate/diff.md) |

`remove` is not used as a fix method. These eight are the deliberately targeted
CVEs; the base refresh is listed in full in [`scans/candidate/diff.md`](scans/candidate/diff.md).

### Residual risk

**465 findings remain, including 25 Critical and 128 High.** This image is more
secure than the original but is **not** "clean". The key fact: **every one of the
465 remaining findings has no fixed version available in Debian bookworm** — Debian
marks them *not-fixed*, *will-not-fix* or *fix-deferred* — so nothing fixable has
been left behind, and no rebuild or bump removes them today.

The Criticals are mostly `curl`/`libcurl4` (16, fix deferred by Debian), plus single
ones in glibc, zlib, libtiff, libxml2 and libaom — and two in nginx itself:

- **CVE-2026-93479** — the natural next backport (see TRIAGE.md); its upstream
  patch doesn't cherry-pick cleanly onto 1.25.5, so it needs conflict resolution.
- **CVE-2026-97205** — no upstream fix yet.

What I'd do next: backport CVE-2026-93479 and VEX it the same way; then stop
patching 1.25.x. nginx 1.25 is an old mainline branch, and the `alias`/`rewrite`
class of bugs keeps appearing in it. A production path would move to a supported
nginx release on a minimal (e.g. distroless) base and rebuild on a schedule.

---

## How it's built

### From source, not apt

`build/build.sh` runs inside a clean `debian:bookworm-slim` and, in order:

1. downloads `nginx-1.25.5.tar.gz` and verifies it against nginx's published SHA-512;
2. fetches nginx's own packaging (`pkg-oss`) at a pinned commit, `14d7f18`: nginx
   `1.25.5-1` and njs packaging release 3 — the same package revisions the original
   image ships (its env says `PKG_RELEASE=1~bookworm`, `NJS_RELEASE=3~bookworm`), so
   configure flags and module builds match;
3. applies the backport patch directly to the source tree and verifies it with a
   reverse dry-run;
4. builds the nginx `.deb`, stamped `1.25.5-1~bookworm+echo1`;
5. fetches njs 0.8.4 — from nginx's contrib mirror with pkg-oss's pinned checksum,
   falling back to njs's GitHub release checked against a SHA-512 pinned in
   `versions.env` (njs's original source host is retired);
6. builds the four module `.deb`s (`nginx-module-geoip`, `-image-filter`, `-njs`,
   `-xslt`) with pkg-oss, each from the same patched source and stamped `+echo1`;
7. deletes the build tree in the same layer, so the build image stays small.

**`nginx -V` of the rebuilt binary has an identical set of configure arguments to
the original** — same modules, paths, user, and `--with-compat`. The only `-V`
differences are the build directory and the newer OpenSSL it was built against.

### Drop-in image

`Containerfile` installs our five `.deb`s onto a clean `debian:bookworm-slim`, and
apt resolves their runtime libraries from the packages' own dependencies:

- the same packages as the original, including `curl`, `ca-certificates` and
  `gettext-base` — checked automatically by `make scan-candidate`;
- the `nginx` user exactly as upstream (uid/gid 101, `nginx user`, `/nonexistent`,
  `/bin/false`), `EXPOSE 80`, `STOPSIGNAL SIGQUIT`, entrypoint and cmd;
- the upstream `/docker-entrypoint.sh` and `/docker-entrypoint.d/` shell scripts,
  reused verbatim (the only thing taken from the upstream image — no binaries);
- log forwarding to the container's stdout/stderr;
- all four dynamic modules as real packages, so scanners can see them — and
  `/usr/bin/njs`, as upstream ships.

Intentional, visible differences: every package we built carries a `+echo1` version
suffix so the rebuild is traceable, which also shows in the two release variables
(`PKG_RELEASE=1~bookworm+echo1`, `NJS_RELEASE=3~bookworm+echo1`). Everything else —
the `nginx` passwd and group entries, the other environment variables, user,
working directory, entrypoint, cmd, ports, stop signal, and the path/type/mode/owner
of every file nginx and the entrypoint own — matches the original, and
`test/contract_test.py` fails if any of it drifts. Also expected: the packaged
files carry our build date, so the default pages' `Last-Modified`/`ETag` headers
differ (contents and sizes are identical). Image size: **278.2 MB vs 273.1 MB** (+1.8%).
With identical package sets, that difference is in what's inside the packages
(newer versions from the refreshed base, and our own builds), not extra components.

---

## Compatibility test

`make test` (pytest, `test/`) boots both images with the same mounted config and
content, then asserts the candidate responds identically to the original across 15
scenarios — static files, 404, HEAD, byte ranges, conditional requests, gzip,
redirect, method-not-allowed, request-too-large, and malformed requests sent over
raw sockets (which a normal HTTP client would "fix" before sending). The only
header ignored is `Date`; gzip bodies are compared decoded. A 16th test proves the
backport changed behaviour, as described above. Scenarios are data
(`test/scenarios.yaml`), so adding a case is a one-line edit.

A second file (`test/module_tls_test.py`) goes past raw parity to the things the
rebuild specifically touched:

- it **loads all six module objects** (http + stream variants of the four modules)
  in both images — the fixture fails to boot if any doesn't load;
- **njs** returns byte-identical output from our compiled module and upstream's;
- **image-filter** produces a valid resized image (not byte-compared — the base
  refresh may carry a newer libgd);
- the candidate serves **TLS** identically to the original (an end-to-end exercise
  of the newer OpenSSL);
- the backport leaves a plain, non-rewritten `alias` untouched — proof the fix is surgical.

A third file (`test/default_test.py`) boots both images **with nothing mounted** —
exactly how someone runs them with `docker run` — because the suites above mount
their own `nginx.conf`, which bypasses the image's packaged config, default pages
and most of the entrypoint:

- the default responses (welcome page, `50x.html`, the default 404 page, `HEAD`) match;
- the **effective configuration** (`nginx -T`, after the entrypoint ran) is identical
  — same packaged `nginx.conf`, `conf.d/default.conf` and `mime.types`, transformed
  the same way;
- the **entrypoint's startup output** matches line for line. Its IPv6 step only edits
  `default.conf` after checking it against the checksum dpkg recorded for the
  package, so this also checks our packaging;
- the entrypoint's **template feature** works the same: a `*.template` file plus an
  environment variable is rendered (via `envsubst`) and served identically.

`test/large_body_test.py` covers the brief's "large body" case in both directions,
where buffering, `sendfile` and temp files actually matter: an 8 MiB download and a
range from its middle must match byte for byte (compared by SHA-256), and a 4 MiB
upload must be *accepted* — WebDAV `PUT` reads the whole body and writes it to disk,
and reading it back must return exactly what was sent. A body that size spills into
`/var/cache/nginx/client_temp`, so this also checks that directory exists and is
writable by the `nginx` user in our image.

A further file (`test/contract_test.py`) checks what no HTTP request can see — the
brief's "filesystem layout, user, working directory, ports, and entrypoint exactly":
image metadata from `docker inspect` (user, workdir, entrypoint, cmd, ports, stop
signal, volumes, platform, every env variable), the `nginx` passwd/group entries, and
the path, type, mode, owner and symlink target of everything under nginx's and the
entrypoint's directories. The only differences it allows are the `+echo1` release
suffix and the image labels.

**Do the tests actually test?** A parity test alone can pass vacuously: if both
images broke the same way (a failed mount, a dropped connection), they would still
"match". So every scenario is **anchored**: it states the status or bytes nginx must
return (`200` plus "Welcome to nginx!", `416`, `HTTP/1.1 400`, an 8×8 resized PNG, …),
checked against upstream *before* the images are compared. And `make selfcheck`
runs the whole suite against images that must fail it:

- **upstream vs itself:** every parity test passes (identical images) and *only* the
  CVE test fails, because that image isn't patched. So the CVE test detects the fix,
  and the parity tests don't flag a correct match.
- **upstream vs nginx 1.27:** 24 tests fail, including all 11 HTTP scenarios, the
  default pages, the large download and range, the env contract, the CVE test and
  3 of the 4 raw-socket cases, as they must for a server that isn't a drop-in.
  (The fourth raw case, HTTP/0.9, rightly passes: it returns the bare page, with
  no status line or version header.)

**What "working correctly" means here:** for every scenario the candidate returns
the same HTTP status, the same response headers (ignoring `Date`, which each server
sets from its own clock), and the same body bytes as the original — and for the one
patched case, it diverges in exactly the intended way. (The one exception is the
default pages' `Last-Modified`/`ETag`, which come from file timestamps — see *Drop-in
image*; their bodies and sizes are still compared.) Any difference fails the
suite with a non-zero exit, so a pass means byte-for-byte parity on everything the
test exercises, not just "it serves a page."

**What it does *not* cover:** performance and concurrency, modules under real load,
the geoip and xslt modules' behaviour beyond loading, and IPv6 traffic (the IPv6
`listen` line is checked through `nginx -T`, but no request is sent over IPv6).
Those are out of scope for a compatibility check of the request-handling
surface — the goal is to catch a behavioural regression from the rebuild, not to
benchmark the server.

---

## Scanning and VEX

The two scanners disagree, which is itself worth noting: **Trivy does not report
CVE-2026-15176 at all; Grype does.** For a backport, where the version can't change,
a scanner that matches on version alone can't tell the code is fixed — so Grype
keeps flagging it on the rebuilt image.

The correct way to resolve that is a **VEX** (Vulnerability Exploitability
eXchange) document: a statement that CVE-2026-15176 is `fixed` in this build,
which a scanner consumes (`grype --vex`) to move the finding to its ignore list.
We ship one at `vex/echo-nginx.openvex.json` (OpenVEX v0.2.0).

It is generated, not hand-written: `tools/make_vex.py` reads the candidate Grype
report and copies the vulnerable package's PURL verbatim, so the document can
never drift from what the scanner actually emitted. The one wrinkle is the
*product* identifier. Grype applies a statement when its product matches the
scanned image and its subcomponent matches the vulnerable package. A locally
built image was never pushed to a registry, so it has no single canonical
reference — Grype may know it by its tag, its image ID, or its manifest digest.
Rather than guess, the generator lists all three as products for the one
statement, so the assertion matches however Grype refers to the image.

`make vex` regenerates the document and re-runs Grype against the candidate with
`--vex --show-suppressed`, then asserts CVE-2026-15176 has moved from the active
match list to the suppressed list — the bonus, done and self-verifying. It is
also the last step of `make all`.

The PCRE2 bump needs no VEX: its version string changes, so both scanners drop
those CVEs on their own.

---

## Repo layout

```text
build/
  Dockerfile              # clean debian:bookworm-slim that runs build.sh
  build.sh                # verify nginx + njs sources, apply patches, build nginx + 4 module .debs
  build-pcre2.sh          # version bump: apt source pcre2 -> dpkg-buildpackage
  Dockerfile.pcre2        # clean base that runs build-pcre2.sh
  patches/
    CVE-2026-15176.patch  # the backport, with DEP-3 provenance
Containerfile             # the drop-in image, with the build gate
scripts/                  # doctor, pin-images, scan, build-deb, build-pcre2, build-image, run-tests, selfcheck, vex
tools/
  triage.py               # merge Trivy + Grype reports into one CVE table
  diff_scans.py           # baseline-vs-candidate diff: fixed vs not-shipped, drop-in package check
  make_vex.py             # generate the OpenVEX doc from the candidate scan
test/                     # pytest suites: compat, large bodies, module/TLS, out-of-the-box, contract
scans/                    # committed reports, package lists, and the diff
vex/                      # OpenVEX doc asserting the backport CVE is fixed
versions.env              # every pinned input (digests, versions, checksums, pkg-oss commit)
TRIAGE.md                 # which CVEs were chosen and why
NOTES.md                  # decisions and the things that broke along the way
```

## What surprised me, and what broke

`NOTES.md` is the running log. The ones worth calling out:

- **The compat test earned its keep:** the backport applied cleanly and compiled,
  but the first build trusted `dpkg` to apply the quilt series and it silently
  didn't — the image shipped *unpatched*. Only the behavioural test caught it.
  "The patch applies cleanly" is not "the patch is in the binary."
- **A near-miss on honesty, caught by auditing against the brief.** An earlier
  version of this image left out `curl` and `ca-certificates`, and its scan diff
  counted every vanished finding as "removed by the rebuild". About 214 of those
  "fixes" were really curl's CVEs disappearing with curl — provable because 38 of
  them have no fix in Debian at all. That made the image less of a drop-in *and*
  made this README's claims false. The fix was both: ship the packages, and make
  the diff tell "fixed" from "not shipped" and fail on any missing package.
- **Modules from source.** That same version copied the four modules' prebuilt
  `.so` files out of the upstream image — repackaged binaries, invisible to the
  scanners. They're now built from source with pkg-oss. Along the way: nginx's
  changelog helper downloads from a dead URL (pre-seeded the changelogs), and
  njs's original source host is retired (contrib mirror first, pinned GitHub
  release as fallback).
- **The build filled the disk.** The module builds left gigabytes of build trees in
  Docker's disk; on WSL the Windows drive filled up mid-scan and corrupted the
  distro. Build trees are now deleted in-layer and `make doctor` checks disk first.
- **Tests that could not fail.** Running the suite against images that *must* fail
  it (`make selfcheck`) exposed tests that passed no matter what: parity checks
  that only compared the two images to each other, and a gzip check whose silent
  `except` swallowed every decode error. Each test is now anchored to what nginx
  must return, and the self-check is part of the deliverable.
- A `set -e` trap: a failed `docker pull` inside a command substitution didn't stop
  the script, hiding the real error behind a later one.

## With more time

- **Backport CVE-2026-93479** — the next nginx Critical — resolving its cherry-pick
  conflict by hand, and VEX it the same way as CVE-2026-15176.
- **Stop patching 1.25.x:** move to a supported nginx release on a minimal base and
  rebuild on a schedule, so most fixes arrive as clean version bumps.
- **Run nginx's own test suite** (pkg-oss can run `nginx-tests` against the built
  binary) in addition to our parity suite, plus performance and concurrency
  comparisons (e.g. with `wrk`), IPv6 traffic, and the geoip/xslt modules' behaviour.
- **Ship evidence with the image, not just in the repo:** sign it, and attach the VEX
  document and an SBOM as OCI attestations (cosign/ORAS), so a scanner can pick them
  up from the registry.
- **Fully hermetic, bit-for-bit reproducible builds:** pin the build toolchain via
  snapshot.debian.org too (only PCRE2's source is pinned that way today), and prove
  it by building twice and comparing the packages.
- **CI:** run `make all` and `make selfcheck` on every pull request.

## Use of AI

I built this with an AI assistant (Claude) and treated it as a fast pair, not an
oracle. It did most of the scaffolding — the scripts, the Dockerfiles and
Containerfile, the test harness, the triage/diff/VEX tools — from my direction,
and helped research the CVEs and nginx's packaging.

Where it helped: speed, and the compatibility suite, which then caught a real bug.
Where it hurt, and I had to catch it:

- **The biggest one:** it built the image without `curl` and `ca-certificates`,
  copied upstream's module binaries instead of compiling them, and then wrote
  README claims ("nothing is removed", "not from dropping anything") that the scan
  data contradicted. I caught it by having it audit the repo line by line against
  the original brief and checking the claims against the scan data.
- It introduced the `set -e` bug above; it first asserted the CVE fix would return
  HTTP 500 when the real patched behaviour is an empty 200 plus a log line; it
  wrote tests that could not fail (see above); and at one point it claimed it had
  updated a file when it hadn't.

I verified every claim against the actual build and scan output rather than taking
its word — which is how both the patch-not-in-the-binary and the not-shipped
problems surfaced.
