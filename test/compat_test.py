"""Compatibility tests: the candidate image must respond identically to the
upstream image across a set of scenarios, and must carry the CVE-2026-15176 fix."""
import pathlib
import re
import socket
import time

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
    # requests advertises gzip on every request by default, which would silently
    # gzip every scenario and leave the plain path untested. Ask for the identity
    # encoding unless a scenario negotiates something else explicitly.
    headers = {"Accept-Encoding": "identity", **(scenario.get("headers") or {})}
    resp = requests.request(
        scenario.get("method", "GET"),
        base + scenario["path"],
        headers=headers,
        data=body,
        allow_redirects=False,
        timeout=10,
    )
    headers = _norm_headers(resp.headers)
    # requests transparently decodes gzip, so resp.content is the payload. The
    # compressed bytes may legitimately differ between builds, so compare the
    # decoded payload; keep Content-Encoding (both must have gzipped), drop the
    # compressed length.
    if headers.get("content-encoding") == "gzip":
        headers.pop("content-length", None)
    return resp.status_code, headers, resp.content


def _fetch_raw(base, payload):
    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=5) as sock:
        sock.sendall(payload.encode("latin-1"))
        raw = b""
        while True:
            try:
                data = sock.recv(4096)
            except TimeoutError:
                break
            if not data:
                break  # server closed the connection
            raw += data
            # Stop as soon as the full response is in: on a kept-alive connection
            # waiting for the server to close would just burn the timeout.
            head, sep, body = raw.partition(b"\r\n\r\n")
            if sep and head.startswith(b"HTTP/"):
                length = re.search(rb"(?im)^content-length:\s*(\d+)", head)
                if length and len(body) >= int(length.group(1)):
                    break
    # drop the Date: header line so two servers compare equal
    keep = [ln for ln in raw.split(b"\r\n") if not ln.lower().startswith(b"date:")]
    return b"\r\n".join(keep)


@pytest.mark.parametrize("scenario", HTTP, ids=[s["name"] for s in HTTP])
def test_http_parity(servers, scenario):
    upstream = _fetch_http(servers["upstream"].base_url, scenario)
    candidate = _fetch_http(servers["candidate"].base_url, scenario)
    # Anchor first: upstream must do what the scenario claims, or a match proves nothing.
    assert upstream[0] == scenario["status"], (
        f"{scenario['name']}: upstream returned {upstream[0]}, scenario expects "
        f"{scenario['status']} -- the scenario no longer tests what it claims"
    )
    if "encoding" in scenario:
        assert upstream[1].get("content-encoding") == scenario["encoding"], (
            f"{scenario['name']}: upstream did not use {scenario['encoding']}")
    else:
        assert "content-encoding" not in upstream[1], (
            f"{scenario['name']}: response was encoded although identity was requested")
    if "body_starts" in scenario:
        assert upstream[2].startswith(scenario["body_starts"].encode()), (
            f"{scenario['name']}: body starts {upstream[2][:30]!r}")
    assert candidate == upstream, (
        f"{scenario['name']}: candidate={candidate!r} upstream={upstream!r}"
    )


@pytest.mark.parametrize("scenario", RAW, ids=[s["name"] for s in RAW])
def test_raw_parity(servers, scenario):
    upstream = _fetch_raw(servers["upstream"].base_url, scenario["payload"])
    candidate = _fetch_raw(servers["candidate"].base_url, scenario["payload"])
    # Anchor: without it, two servers that both just close the connection would
    # "match" on empty bytes.
    assert upstream.startswith(scenario["expect"].encode()), (
        f"{scenario['name']}: upstream replied {upstream[:60]!r}, expected it to "
        f"start with {scenario['expect']!r}"
    )
    assert candidate == upstream, (
        f"{scenario['name']}: candidate={candidate!r} upstream={upstream!r}"
    )


def _logged(server, needle, timeout=5.0):
    """Docker delivers container logs asynchronously, so poll briefly instead of
    racing it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if needle in server.logs():
            return True
        time.sleep(0.2)
    return needle in server.logs()


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
    assert _logged(servers["candidate"], guard), (
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
