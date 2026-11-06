# Baseline vs candidate scan diff

- Baseline findings:  846
- Candidate findings: 357
- **Removed by the rebuild: 489**  (Critical: 47 | High: 201 | Medium: 173 | Low: 57 | Unknown: 11)
- Still present: 357  (Critical: 9 | High: 89 | Medium: 109 | Low: 110 | Negligible: 2 | Unknown: 38)

## Version bump: PCRE2 (7 removed)

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

Still reported by the scanner (the package version is unchanged), as expected for a backport. This is the VEX candidate.

## Largest removed groups

- curl: 104
- openssl: 97
- krb5: 52
- expat: 33
- gnutls28: 21
- libxml2: 21
- glibc: 18
- perl: 16
- systemd: 14
- libde265: 12
- libpng1.6: 12
- tiff: 9
