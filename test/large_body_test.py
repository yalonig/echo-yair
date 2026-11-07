"""Large bodies, both directions (the brief's "large body" case). The parity
scenarios use small files; these move megabytes, where buffering, sendfile and
temp-file handling actually come into play. Bodies are compared by SHA-256 so a
failure message never dumps megabytes.

 - an 8 MiB download (deterministic, incompressible, generated per run) and a
   range from its middle must match on both images, byte for byte;
 - a 4 MiB upload must be ACCEPTED and fully read: WebDAV PUT writes it to disk,
   GET returns it, and the hash must equal what was sent. The body spills into
   /var/cache/nginx/client_temp, so this also checks that directory's ownership.
"""
import hashlib
import random

import requests

from conftest import LARGE_FILE_BYTES, large_file_bytes

VOLATILE = {"date"}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _get(base, path, **headers):
    resp = requests.get(base + path, headers={"Accept-Encoding": "identity", **headers}, timeout=30)
    stable = {k.lower(): v for k, v in resp.headers.items() if k.lower() not in VOLATILE}
    return resp.status_code, stable, _sha(resp.content), len(resp.content)


def test_large_download_parity(servers):
    expected = _sha(large_file_bytes())
    up = _get(servers["upstream"].base_url, "/large/large.bin")
    cand = _get(servers["candidate"].base_url, "/large/large.bin")
    # Anchor: upstream really served the whole 8 MiB file intact.
    assert up[0] == 200 and up[3] == LARGE_FILE_BYTES and up[2] == expected, up[:1] + up[2:]
    assert cand == up, f"candidate={cand[0]} {cand[3]}B {cand[2][:12]} vs upstream={up[0]} {up[3]}B {up[2][:12]}"


def test_large_range_parity(servers):
    start = LARGE_FILE_BYTES // 2
    rng = f"bytes={start}-{start + 65535}"
    expected = _sha(large_file_bytes()[start:start + 65536])
    up = _get(servers["upstream"].base_url, "/large/large.bin", Range=rng)
    cand = _get(servers["candidate"].base_url, "/large/large.bin", Range=rng)
    assert up[0] == 206 and up[3] == 65536 and up[2] == expected, up[:1] + up[2:]
    assert cand == up, f"candidate={cand} upstream={up}"


def test_large_upload_roundtrip(servers):
    body = random.Random(7).randbytes(4 * 1024 * 1024)
    results = {}
    for name, server in servers.items():
        put = requests.put(server.base_url + "/dav/upload.bin", data=body, timeout=30)
        back = requests.get(server.base_url + "/dav/upload.bin",
                            headers={"Accept-Encoding": "identity"}, timeout=30)
        results[name] = (put.status_code, back.status_code, _sha(back.content))
    # Anchor: upstream accepted it (201 Created) and returned exactly what was sent.
    assert results["upstream"] == (201, 200, _sha(body)), results["upstream"]
    assert results["candidate"] == results["upstream"], results
