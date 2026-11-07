#!/usr/bin/env python3
"""Merge Trivy and Grype JSON reports into one per-CVE triage table."""

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Iterable, Iterator

SEVERITY_ORDER = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
COLUMNS = (
    "cve",
    "severity",
    "package",
    "source_package",
    "installed_version",
    "fixed_version",
    "fix_state",
    "scanners",
    "suggested_method",
    "title",
)


@dataclass
class Finding:
    scanner: str
    cve: str
    package: str
    installed: str
    severity: str
    fixed: str = ""
    fix_state: str = ""
    source_package: str = ""
    title: str = ""


@dataclass
class TriageRow:
    cve: str
    package: str
    installed: str
    severity: str = "Unknown"
    source_package: str = ""
    fixed: str = ""
    fix_states: set[str] = field(default_factory=set)
    scanners: set[str] = field(default_factory=set)
    title: str = ""


def normalize_severity(value: str | None) -> str:
    severity = (value or "").strip().capitalize()
    return severity if severity in SEVERITY_ORDER else "Unknown"


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.index(severity)


def parse_trivy(report: dict) -> Iterator[Finding]:
    for result in report.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            yield Finding(
                scanner="trivy",
                cve=vuln["VulnerabilityID"],
                package=vuln["PkgName"],
                installed=vuln.get("InstalledVersion", ""),
                severity=normalize_severity(vuln.get("Severity")),
                fixed=vuln.get("FixedVersion", ""),
                fix_state=vuln.get("Status", ""),
                title=vuln.get("Title", ""),
            )


def parse_grype(report: dict) -> Iterator[Finding]:
    for match in report.get("matches") or []:
        vuln = match["vulnerability"]
        artifact = match["artifact"]
        fix = vuln.get("fix") or {}
        upstreams = artifact.get("upstreams") or []
        yield Finding(
            scanner="grype",
            cve=vuln["id"],
            package=artifact["name"],
            installed=artifact.get("version", ""),
            severity=normalize_severity(vuln.get("severity")),
            fixed=", ".join(fix.get("versions") or []),
            fix_state=fix.get("state", ""),
            source_package=upstreams[0].get("name", "") if upstreams else "",
        )


def is_nginx(row: TriageRow) -> bool:
    return (row.source_package or row.package).startswith("nginx")


# The first matching rule wins. Add a method by adding a rule.
METHOD_RULES: tuple[tuple[Callable[[TriageRow], bool], str], ...] = (
    (is_nginx, "backport"),
    (lambda row: bool(row.fixed), "bump"),
)


def suggest_method(row: TriageRow) -> str:
    for matches, method in METHOD_RULES:
        if matches(row):
            return method
    return "no fix available"


def merge(findings: Iterable[Finding]) -> list[TriageRow]:
    rows: dict[tuple[str, str], TriageRow] = {}
    for finding in findings:
        row = rows.setdefault(
            (finding.cve, finding.package),
            TriageRow(finding.cve, finding.package, finding.installed),
        )
        if severity_rank(finding.severity) < severity_rank(row.severity):
            row.severity = finding.severity
        row.source_package = row.source_package or finding.source_package
        row.fixed = row.fixed or finding.fixed
        row.title = row.title or finding.title
        row.scanners.add(finding.scanner)
        if finding.fix_state:
            row.fix_states.add(finding.fix_state)
    return sorted(
        rows.values(),
        key=lambda row: (severity_rank(row.severity), row.package, row.cve),
    )


def write_csv(rows: list[TriageRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow(
                (
                    row.cve,
                    row.severity,
                    row.package,
                    row.source_package or row.package,
                    row.installed,
                    row.fixed,
                    "; ".join(sorted(row.fix_states)),
                    "+".join(sorted(row.scanners)),
                    suggest_method(row),
                    row.title,
                )
            )


def print_summary(rows: list[TriageRow]) -> None:
    print(f"Findings: {len(rows)}")
    by_severity = Counter(row.severity for row in rows)
    for severity in SEVERITY_ORDER:
        print(f"  {severity:<11}{by_severity[severity]}")
    by_method = Counter(suggest_method(row) for row in rows)
    print("Suggested method:")
    for method, count in by_method.most_common():
        print(f"  {method:<17}{count}")
    by_scanner = Counter("+".join(sorted(row.scanners)) for row in rows)
    print("Found by:")
    for scanners, count in by_scanner.most_common():
        print(f"  {scanners:<17}{count}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trivy", type=Path, required=True)
    parser.add_argument("--grype", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    findings = [*parse_trivy(load(args.trivy)), *parse_grype(load(args.grype))]
    rows = merge(findings)
    write_csv(rows, args.output)
    print_summary(rows)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
