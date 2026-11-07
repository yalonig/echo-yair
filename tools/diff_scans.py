#!/usr/bin/env python3
"""Diff two triage CSVs (baseline vs candidate) and say WHY each finding went away.

A finding can disappear from the candidate scan for two very different reasons:

  * fixed   -- the package is still shipped, at a newer (patched) version. This
               is real remediation (a version bump, or a base refresh).
  * missing -- the package is not in the candidate image at all. That is
               component removal, which the brief says does not count -- and for
               a drop-in it is usually a regression, not a fix.

Telling them apart needs each image's package list (scan.sh writes
<prefix>-packages.txt). With --fail-on-missing, any upstream package absent from
the candidate fails the run, so "nothing was removed" can never silently be false.
A CVE that remains because its version did not change is a VEX candidate."""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

SEVERITY_ORDER = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
BACKPORT_CVE = "CVE-2026-15176"
BUMP_PACKAGE = "libpcre2-8-0"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8", newline="") as handle:
        return {(row["cve"], row["package"]): row for row in csv.DictReader(handle)}


def load_packages(path):
    if path is None or not path.is_file():
        return None
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def severity_table(rows) -> str:
    counts = Counter(r["severity"] for r in rows)
    cells = " | ".join(f"{s}: {counts.get(s, 0)}" for s in SEVERITY_ORDER if counts.get(s))
    return cells or "none"


def md_table(rows) -> str:
    rows = sorted(rows, key=lambda r: (SEVERITY_ORDER.index(r["severity"]), r["package"], r["cve"]))
    lines = ["| CVE | Severity | Package | Installed | Fixed in |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['cve']} | {r['severity']} | {r['package']} | "
                     f"{r['installed_version']} | {r['fixed_version'] or '-'} |")
    return "\n".join(lines)


def groups(rows, n=12):
    return [f"- {pkg}: {k}" for pkg, k in
            Counter(r["source_package"] or r["package"] for r in rows).most_common(n)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--baseline-packages", type=Path)
    ap.add_argument("--candidate-packages", type=Path)
    ap.add_argument("--fail-on-missing", action="store_true",
                    help="exit non-zero if an upstream package is missing from the candidate")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    base, cand = load(args.baseline), load(args.candidate)
    base_pkgs = load_packages(args.baseline_packages)
    cand_pkgs = load_packages(args.candidate_packages)
    have_inventory = base_pkgs is not None and cand_pkgs is not None

    removed = [base[k] for k in base if k not in cand]
    remaining = [cand[k] for k in cand if k in base]
    added = [cand[k] for k in cand if k not in base]

    if have_inventory:
        missing_pkgs = sorted(base_pkgs - cand_pkgs)
        fixed = [r for r in removed if r["package"] in cand_pkgs]
        not_shipped = [r for r in removed if r["package"] not in cand_pkgs]
    else:
        missing_pkgs, fixed, not_shipped = None, removed, []

    out = ["# Baseline vs candidate scan diff\n",
           f"- Baseline findings:  {len(base)}",
           f"- Candidate findings: {len(cand)}"]
    if have_inventory:
        out.append(f"- **Fixed (package still shipped, newer version): {len(fixed)}**  ({severity_table(fixed)})")
        out.append(f"- Gone because the package is not shipped: {len(not_shipped)}  ({severity_table(not_shipped)})")
    else:
        out.append(f"- **Gone from the candidate scan: {len(removed)}**  ({severity_table(removed)})  "
                   "_(no package inventories: cannot tell fixed from not-shipped)_")
    out.append(f"- Still present: {len(remaining)}  ({severity_table(remaining)})")
    if added:
        out.append(f"- Newly reported: {len(added)}  ({severity_table(added)})")
    out.append("")

    out.append("## Drop-in check: upstream packages missing from the candidate\n")
    if missing_pkgs is None:
        out.append("_Package inventories not available; run both scans to produce them._")
    elif missing_pkgs:
        out.append(f"**{len(missing_pkgs)} upstream package(s) are not shipped:** "
                   + ", ".join(f"`{p}`" for p in missing_pkgs))
    else:
        out.append(f"None: every one of the {len(base_pkgs)} packages in the upstream image is "
                   "also in the candidate, so no finding was removed by dropping a component.")
    out.append("")

    pcre = [r for r in fixed if r["package"] == BUMP_PACKAGE]
    out.append(f"## Version bump: PCRE2 ({len(pcre)} fixed)\n")
    out.append(md_table(pcre) if pcre else "_No PCRE2 CVEs fixed — check the rebuild._")
    out.append("")

    out.append(f"## Backport: {BACKPORT_CVE}\n")
    out.append("Still reported by the scanner (the package version is unchanged), as expected "
               "for a backport. This is the VEX candidate; see `make vex`.\n"
               if any(cve == BACKPORT_CVE for cve, _ in cand)
               else "Not present in the candidate scan.\n")

    out.append("## Largest fixed groups (newer versions from the current base)\n")
    out.extend(groups([r for r in fixed if r["package"] != BUMP_PACKAGE]))
    out.append("")
    if not_shipped:
        out.append("## Gone because the package is not shipped (does not count)\n")
        out.extend(groups(not_shipped))
        out.append("")

    text = "\n".join(out)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)

    if args.fail_on_missing and missing_pkgs:
        print(f"\nERROR: {len(missing_pkgs)} upstream package(s) missing from the candidate: "
              + " ".join(missing_pkgs), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
