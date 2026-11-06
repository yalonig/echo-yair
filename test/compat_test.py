"""Compatibility tests: the candidate image must respond identically to the
upstream image across a set of scenarios, and must carry the CVE-2026-15176 fix."""
import gzip
import pathlib
import socket

import pytest
import requests
import yaml

HERE = pathlib.Path(__file__).parent
SCENARIOS = yaml.safe_load((HERE / "scenarios.yaml").read_text())
HTTP = [s for s in SCENARIOS if s["kind"] == "http"]
RAW = [s for s in SCENARIOS if s["kind"] == "raw"]

# Headers that legitimately differ between two running servers.
VOLATILE_HEADERS = {"date"}


def _norm_headers(headers):
    return {k.lower(): v for k, v in headers.items() if k.lower() not in VOLATILE_HEADERS}


def _fetch_http(base, scenario):
    body = b"x" * scenario["body_bytes"] if "body_bytes" in scenario else None
    resp = requests.request(
        scenario.get("method", "GET"),
        base + scenario["path"],
        headers=scenario.get("headers"),
        data=body,
        allow_redirects=False,
        timeout=10,
    )
    headers = _norm_headers(resp.headers)
    content = resp.content
    # gzip framing can differ byte-for-byte; compare the decoded payload instead.
    if headers.get("content-encoding") == "gzip":
        try:
            content = gzip.decompress(content)
        except OSError:
            pass
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
    return resp.status_code, headers, content


def _fetch_raw(base, payload):
    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=5) as sock:
        sock.sendall(payload.encode("latin-1"))
        sock.settimeout(5)
        chunks = []
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
        except socket.timeout:
            pass
    raw = b"".join(chunks)
    # drop the Date: header line so two servers compare equal
    keep = [ln for ln in raw.split(b"\r\n") if not ln.lower().startswith(b"date:")]
    return b"\r\n".join(keep)


@pytest.mark.parametrize("scenario", HTTP, ids=[s["name"] for s in HTTP])
def test_http_parity(servers, scenario):
    upstream = _fetch_http(servers["upstream"].base_url, scenario)
    candidate = _fetch_http(servers["candidate"].base_url, scenario)
    assert candidate == upstream, (
        f"{scenario['name']}: candidate={candidate!r} upstream={upstream!r}"
    )


@pytest.mark.parametrize("scenario", RAW, ids=[s["name"] for s in RAW])
def test_raw_parity(servers, scenario):
    upstream = _fetch_raw(servers["upstream"].base_url, scenario["payload"])
    candidate = _fetch_raw(servers["candidate"].base_url, scenario["payload"])
    assert candidate == upstream, (
        f"{scenario['name']}: candidate={candidate!r} upstream={upstream!r}"
    )


def test_cve_2026_15176_is_fixed(servers):
    """The backport adds a guard in ngx_http_map_uri_to_path(). On the alias+rewrite
    trigger the patched build refuses to map $request_filename -- it logs an alert
    and returns an empty body -- while the upstream build maps the path and returns
    it. Both answer 200; the fix is visible in the error log and the response body."""
    path = "/foo/1"
    guard = "where URI was rewritten"

    candidate = requests.get(servers["candidate"].base_url + path, timeout=10)
    upstream = requests.get(servers["upstream"].base_url + path, timeout=10)

    # The guard fires on the patched build only.
    assert guard in servers["candidate"].logs(), (
        "patched build should log the alias/rewrite guard for the trigger request"
    )
    assert guard not in servers["upstream"].logs(), (
        "upstream build should not log the guard (it lacks the fix)"
    )

    # The observable response diverges: the patched build maps nothing (empty body),
    # the upstream build returns the mapped $request_filename.
    assert candidate.content != upstream.content, (
        f"expected divergent bodies; candidate={candidate.content!r} "
        f"upstream={upstream.content!r}"
    )
    assert candidate.content == b"", (
        f"patched build should return no mapped path, got {candidate.content!r}"
    )
