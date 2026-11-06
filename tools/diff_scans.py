#!/usr/bin/env python3
"""Diff two triage CSVs (baseline vs candidate) to show which CVEs the rebuild
removed and which remain. Removed library CVEs are the version-bump remediation;
a CVE that remains because its version did not change is a VEX candidate."""

import argparse
import csv
from collections import Counter
from pathlib import Path

SEVERITY_ORDER = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")


def load(path: Path) -> dict:
    with path.open(encoding="utf-8", newline="") as handle:
        return {(row["cve"], row["package"]): row for row in csv.DictReader(handle)}


def severity_table(rows) -> str:
    counts = Counter(r["severity"] for r in rows)
    cells = " | ".join(f"{s}: {counts.get(s, 0)}" for s in SEVERITY_ORDER if counts.get(s))
    return cells or "none"


def md_table(rows, limit=None) -> str:
    rows = sorted(
        rows, key=lambda r: (SEVERITY_ORDER.index(r["severity"]), r["package"], r["cve"])
    )
    if limit:
        rows = rows[:limit]
    lines = ["| CVE | Severity | Package | Installed | Fixed in |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['cve']} | {r['severity']} | {r['package']} | "
            f"{r['installed_version']} | {r['fixed_version'] or '-'} |"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    base = load(args.baseline)
    cand = load(args.candidate)

    removed = [base[k] for k in base if k not in cand]
    remaining = [cand[k] for k in cand if k in base]
    added = [cand[k] for k in cand if k not in base]

    report = []
    report.append("# Baseline vs candidate scan diff\n")
    report.append(f"- Baseline findings:  {len(base)}")
    report.append(f"- Candidate findings: {len(cand)}")
    report.append(f"- **Removed by the rebuild: {len(removed)}**  ({severity_table(removed)})")
    report.append(f"- Still present: {len(remaining)}  ({severity_table(remaining)})")
    if added:
        report.append(f"- Newly introduced: {len(added)}  ({severity_table(added)})")
    report.append("")

    # The two CVEs the project set out to fix.
    pcre = [r for r in removed if r["package"] == "libpcre2-8-0"]
    report.append(f"## Version bump: PCRE2 ({len(pcre)} removed)\n")
    report.append(md_table(pcre) if pcre else "_No PCRE2 CVEs removed — check the rebuild._")
    report.append("")

    backport_present = any(cve == "CVE-2026-15176" for cve, _ in cand)
    report.append("## Backport: CVE-2026-15176\n")
    report.append(
        "Still reported by the scanner (the package version is unchanged), as "
        "expected for a backport. This is the VEX candidate.\n"
        if backport_present
        else "Not present in the candidate scan.\n"
    )

    report.append("## Largest removed groups\n")
    by_pkg = Counter(r["source_package"] or r["package"] for r in removed)
    for pkg, n in by_pkg.most_common(12):
        report.append(f"- {pkg}: {n}")
    report.append("")

    text = "\n".join(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nRemoved {len(removed)} findings; {len(remaining)} remain.")


if __name__ == "__main__":
    main()
