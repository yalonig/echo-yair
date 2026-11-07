"""Checks beyond raw response parity, tied to the specific remediation work:

 - all four dynamic modules (which we compile from source) load in both images
   -- the fixture loads all six module objects, so a bad module fails to boot --
   and two of them behave: our njs matches upstream's byte-for-byte, and
   image-filter produces a valid image;
 - the TLS listener serves (exercises the newer OpenSSL end to end, not just
   its version string);
 - the CVE-2026-15176 backport is surgical: a plain alias (no rewrite) is
   untouched.

These use the ext_servers fixture (fixtures/nginx-ext.conf)."""
import struct
import warnings

import requests
import urllib3

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _get(url, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
        return requests.get(url, timeout=10, **kw)


def test_njs_module_parity(ext_servers):
    """njs output is deterministic JS with no external library, so the two
    builds must return it byte-for-byte identically -- proving the njs module
    loads and runs the same in the rebuild."""
    up = _get(ext_servers["upstream"].base_url + "/njs")
    cand = _get(ext_servers["candidate"].base_url + "/njs")
    assert cand.status_code == up.status_code == 200, (
        f"status: candidate={cand.status_code} upstream={up.status_code}"
    )
    assert cand.content == up.content == b"njs-ok\n", (
        f"body: candidate={cand.content!r} upstream={up.content!r}"
    )


def test_image_filter_module_works(ext_servers):
    """image-filter links libgd, which the rebuild may update, so assert the
    module FUNCTIONS (returns a valid, resized PNG) on both builds rather than
    demanding byte parity on bytes libgd is entitled to change."""
    for name in ("upstream", "candidate"):
        resp = _get(ext_servers[name].base_url + "/pic.png")
        assert resp.status_code == 200, f"{name}: status {resp.status_code}"
        assert resp.headers.get("content-type", "").startswith("image/"), (
            f"{name}: content-type {resp.headers.get('content-type')!r}"
        )
        assert resp.content[:8] == PNG_MAGIC, f"{name}: output is not a PNG"
        # The PNG IHDR chunk carries width/height at bytes 16..24. The source is
        # 64x64, so 8x8 proves the filter actually ran (not a pass-through).
        width, height = struct.unpack(">II", resp.content[16:24])
        assert (width, height) == (8, 8), f"{name}: got {width}x{height}, filter did not resize"


def test_tls_listener_parity(ext_servers):
    """The candidate serves HTTPS identically to upstream -- this is the end-to-
    end exercise of the newer OpenSSL, beyond the version-string check in the
    Containerfile gate."""
    for path in ("/", "/njs"):
        up = _get(ext_servers["upstream"].https_url + path, verify=False)
        cand = _get(ext_servers["candidate"].https_url + path, verify=False)
        assert cand.status_code == up.status_code, (
            f"{path} status: candidate={cand.status_code} upstream={up.status_code}"
        )
        assert cand.content == up.content, f"{path} body differs"


def test_backport_leaves_plain_alias_untouched(ext_servers):
    """The guard rejects alias mapping only AFTER a rewrite. A plain alias (no
    rewrite) must still serve files, identically on both builds -- proof the
    backport is surgical rather than disabling alias wholesale. The real check is
    the 200 with identical content; the "guard not logged" assertion is only a
    sanity check (this config has no rewrite, so it should never fire anyway)."""
    guard = "where URI was rewritten"
    up = _get(ext_servers["upstream"].base_url + "/alias-ok/index.html")
    cand = _get(ext_servers["candidate"].base_url + "/alias-ok/index.html")
    assert cand.status_code == up.status_code == 200, (
        f"status: candidate={cand.status_code} upstream={up.status_code}"
    )
    assert cand.content == up.content, "plain alias should serve identically"
    assert b"echo-nginx compatibility fixture" in cand.content, (
        "plain alias did not serve the fixture's index.html")
    assert guard not in ext_servers["candidate"].logs(), (
        "plain alias (no rewrite) must not trigger the CVE-2026-15176 guard"
    )
