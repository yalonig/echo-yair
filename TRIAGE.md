# Triage

## How this was scanned

Both scanners ran against the upstream image pinned by digest
(`nginx:1.25-bookworm@sha256:a484819e…`), so the baseline is reproducible even
after the tag moves. `tools/triage.py` merges the two JSON reports into one row
per (CVE, package) in `scans/baseline/baseline-triage.csv`; tool and database
versions are recorded in `scans/baseline/baseline-meta.txt`.

- Image OS: Debian 12.5, nginx `1.25.5-1~bookworm`
- Trivy 0.76.2 (DB 2, 2026-11-06), Grype 0.121.2 (DB v6.1.10, 2026-11-06)
- Total merged findings: 846 (56 Critical, 290 High)

The count is large because it includes every transitive library in the base
image. Per the brief, the goal is two CVEs fixed end-to-end with two different
techniques, not shrinking the whole list.

## The two CVEs we are fixing

| CVE | Package | Lives in | Upstream fix | Our method |
|---|---|---|---|---|
| CVE-2026-15176 | nginx | `ngx_http_core_module` (the nginx binary itself) | nginx 1.31.7 / 1.30.6 | **Backport** |
| CVE-2026-86145 + 6 more | libpcre2-8-0 | PCRE2 regex engine nginx links | Debian `10.42-1+deb12u2` | **Version bump** |

### Backport — CVE-2026-15176 (nginx)

- **Where it lives:** the nginx binary, function `ngx_http_map_uri_to_path()` in
  `src/http/ngx_http_core_module.c`.
- **The bug:** in a `location` that uses `alias` together with `rewrite`, the
  rewritten URI can be shorter than the location prefix. When nginx builds the
  file path it writes past the allocated buffer. An unauthenticated request is
  enough. The upstream commit gives a trigger config and the request `/foo/1`.
- **Upstream fix:** commit `f8a23425` ("Avoid post-rewrite URI to path mapping
  with alias"), first released in 1.31.7 / 1.30.6. It is a one-line guard:
  reject the path mapping when `r->uri_changed` is set.
- **Why backport, not bump:** we ship a 1.25.x package to stay a drop-in
  replacement, so we cannot move to 1.31.7. We port the fix onto 1.25.5 instead.
  The commit cherry-picks onto `release-1.25.5` cleanly.
- **Scanner consequence:** the package version string stays `1.25.5`, so Trivy
  and Grype keep flagging it even after the source is patched. This is the case
  the VEX document exists for — we declare it `fixed` and the scanner drops it.
- **Severity note:** Grype rates this Critical (CVSS 9.2); nginx.org rates it
  medium. We clear it either way, but the gap is worth knowing — scanner
  severity is not the same as vendor severity.

### Version bump — PCRE2 (libpcre2-8-0)

- **Where it lives:** PCRE2, the regular-expression engine. nginx links it and
  uses it for every regex in a config (`location ~`, `map`, `rewrite`, …), so
  it is a genuine part of the attack surface, not an incidental library.
- **The bugs:** the image ships PCRE2 `10.42-1`. Seven CVEs apply, led by
  CVE-2026-86145, a High-severity out-of-bounds write described as allowing
  arbitrary code execution via a crafted pattern.
- **Upstream fix:** Debian fixes these in `10.42-1+deb12u1` and `+deb12u2`.
  Rebuilding PCRE2 at `10.42-1+deb12u2` clears all seven at once:

  | CVE | Severity | Fixed in |
  |---|---|---|
  | CVE-2026-103111 | High | 10.42-1+deb12u2 |
  | CVE-2026-86145 | High | 10.42-1+deb12u1 |
  | CVE-2026-89157 | High | 10.42-1+deb12u1 |
  | CVE-2026-89161 | High | 10.42-1+deb12u1 |
  | CVE-2026-89156 | Medium | 10.42-1+deb12u1 |
  | CVE-2026-89158 | Medium | 10.42-1+deb12u1 |
  | CVE-2026-89160 | Medium | 10.42-1+deb12u1 |

- **Why bump, not backport:** the fixed source already exists in Debian. We
  rebuild it from that source and install the `.deb`. Because the version string
  changes, the scanner sees the fix on its own — no VEX needed.

## Why this pair

- **Two genuinely different techniques.** The backport is a hand-applied source
  patch where the version cannot change; the bump is a clean rebuild where the
  version does change. They exercise the two halves of the brief and they
  demonstrate the two different ways a scanner reacts (VEX-suppressed vs.
  naturally dropped).
- **Both are real in this image.** Both come straight from the scan, not from a
  blog's go-to example. CVE-2024-7347 (the usual nginx backport demo) is *not*
  in the report — Debian already fixed it and 1.25.5 is past the fixed version —
  so backporting it would prove nothing.
- **Both are explainable and demonstrable.** The nginx overflow has a published
  trigger config; the PCRE2 fix is a visible version change.

## Considered and not chosen

- **CVE-2026-93479 (nginx, script evaluation overflow):** also a good backport,
  but the upstream patch does not cherry-pick cleanly onto 1.25.5. A candidate
  for a second backport if time allows, to show conflict resolution.
- **OpenSSL (libssl3):** the most Critical findings, but a heavy rebuild and we
  would clear only the subset fixed by our target version. PCRE2 is lighter and
  more directly tied to how nginx parses configuration.
- **zlib (zlib1g):** flagged, but Debian marks the open issues `will_not_fix` /
  not-fixed, so there is no version to bump to.
