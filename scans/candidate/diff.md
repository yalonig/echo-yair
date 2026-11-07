# Baseline vs candidate scan diff

- Baseline findings:  846
- Candidate findings: 465
- **Fixed (package still shipped, newer version): 381**  (Critical: 31 | High: 162 | Medium: 158 | Low: 19 | Unknown: 11)
- Gone because the package is not shipped: 0  (none)
- Still present: 465  (Critical: 25 | High: 128 | Medium: 124 | Low: 148 | Negligible: 2 | Unknown: 38)

## Drop-in check: upstream packages missing from the candidate

None: every one of the 149 packages in the upstream image is also in the candidate, so no finding was removed by dropping a component.

## Version bump: PCRE2 (7 fixed)

| CVE | Severity | Package | Installed | Fixed in |
|---|---|---|---|---|
| CVE-2026-103111 | High | libpcre2-8-0 | 10.42-1 | 10.42-1+deb12u2 |
| CVE-2026-86145 | High | libpcre2-8-0 | 10.42-1 | 10.42-1+deb12u1 |
| CVE-2026-89157 | High | libpcre2-8-0 | 10.42-1 | 10.42-1+deb12u1 |
| CVE-2026-89161 | High | libpcre2-8-0 | 10.42-1 | 10.42-1+deb12u1 |
| CVE-2026-89156 | Medium | libpcre2-8-0 | 10.42-1 | 10.42-1+deb12u1 |
| CVE-2026-89158 | Medium | libpcre2-8-0 | 10.42-1 | 10.42-1+deb12u1 |
| CVE-2026-89160 | Medium | libpcre2-8-0 | 10.42-1 | 10.42-1+deb12u1 |

## Backport: CVE-2026-15176

Still reported by the scanner (the package version is unchanged), as expected for a backport. This is the VEX candidate; see `make vex`.

## Largest fixed groups (newer versions from the current base)

- openssl: 96
- expat: 33
- krb5: 28
- curl: 28
- gnutls28: 21
- libxml2: 21
- glibc: 18
- perl: 16
- systemd: 14
- libde265: 12
- libpng1.6: 12
- tiff: 9
