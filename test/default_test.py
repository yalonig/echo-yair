"""Out-of-the-box parity: both images booted with NO mounted config, exactly as
someone runs them with `docker run`. The other suites mount their own nginx.conf,
which bypasses the image's packaged config, its default pages and most of its
entrypoint. This suite covers that surface:

 - default responses (welcome page, 50x page, default 404) match;
 - the effective configuration (`nginx -T`) is identical -- the packaged
   nginx.conf, conf.d/default.conf and mime.types, after the entrypoint ran;
 - the entrypoint's startup output matches line for line (its IPv6 step only
   edits default.conf after checking it against the checksum dpkg recorded for
   the package, so this also checks our packaging);
 - the entrypoint's template feature (envsubst) renders and serves identically.
"""
import difflib

import pytest
import requests

from conftest import TEMPLATE_GREETING

# Last-Modified and ETag come from the html files' mtimes, i.e. the package build
# time: upstream built its package in 2024, we built ours from source today. The
# bodies are compared byte-for-byte, and ETag's size half is compared too.
TIMESTAMP_HEADERS = {"date", "last-modified", "etag"}

# (name, method, path, status upstream must return, bytes its body must contain)
DEFAULT_SCENARIOS = [
    ("welcome_root", "GET", "/", 200, b"<title>Welcome to nginx!</title>"),
    ("welcome_index", "GET", "/index.html", 200, b"<title>Welcome to nginx!</title>"),
    ("error_page_50x", "GET", "/50x.html", 200, b"An error occurred."),
    ("default_404", "GET", "/does-not-exist", 404, b"404 Not Found"),
    ("head_root", "HEAD", "/", 200, b""),
]


def _fetch(base, method, path, **kwargs):
    resp = requests.request(method, base + path, allow_redirects=False, timeout=10, **kwargs)
    headers = {k.lower(): v for k, v in resp.headers.items()}
    stable = {k: v for k, v in headers.items() if k not in TIMESTAMP_HEADERS}
    return resp.status_code, stable, resp.content, headers


def _etag_size(etag):
    return etag.strip('"').rsplit("-", 1)[-1]  # nginx ETag: "<hex mtime>-<hex size>"


def _diff(a, b, a_name="upstream", b_name="candidate"):
    return "\n".join(difflib.unified_diff(
        a.splitlines(), b.splitlines(), a_name, b_name, lineterm="", n=2))


@pytest.mark.parametrize("name,method,path,status,marker", DEFAULT_SCENARIOS,
                         ids=[s[0] for s in DEFAULT_SCENARIOS])
def test_default_config_parity(default_servers, name, method, path, status, marker):
    up = _fetch(default_servers["upstream"].base_url, method, path)
    cand = _fetch(default_servers["candidate"].base_url, method, path)
    # Anchor: upstream serves the real default page, so a match is meaningful.
    assert up[0] == status and marker in up[2], (
        f"{name}: upstream returned {up[0]} without {marker!r}")
    if method == "HEAD":
        assert up[2] == b"", f"{name}: HEAD returned a body"
    assert cand[:3] == up[:3], f"{name}: candidate={cand[:3]!r} upstream={up[:3]!r}"
    up_h, cand_h = up[3], cand[3]
    for header in ("last-modified", "etag"):
        assert (header in cand_h) == (header in up_h), f"{name}: {header} on one image only"
    if "etag" in up_h:
        assert _etag_size(cand_h["etag"]) == _etag_size(up_h["etag"]), (
            f"{name}: ETag size half differs: {cand_h['etag']} vs {up_h['etag']}")


def test_effective_config_parity(default_servers):
    """`nginx -T` prints the complete configuration nginx actually loaded. Equal
    output means the packaged config files are identical AND the entrypoint
    transformed them identically (e.g. the IPv6 listen it adds to default.conf)."""
    up = default_servers["upstream"].exec("nginx", "-T").stdout
    cand = default_servers["candidate"].exec("nginx", "-T").stdout
    assert up.strip(), "upstream nginx -T printed nothing"
    assert cand == up, "effective config differs:\n" + _diff(up, cand)


def test_entrypoint_startup_parity(default_servers):
    """The entrypoint scripts must take the same path on both images."""
    up = default_servers["upstream"].startup_lines()
    cand = default_servers["candidate"].startup_lines()
    assert any("ready for start up" in line for line in up), (
        "upstream entrypoint output not found:\n" + "\n".join(up))
    assert cand == up, "entrypoint output differs:\n" + _diff("\n".join(up), "\n".join(cand))


def test_envsubst_template_parity(template_servers):
    """A /etc/nginx/templates/*.template plus an env var is rendered into
    conf.d/ by the entrypoint (needs gettext-base's envsubst) and served."""
    results = {}
    for name, server in template_servers.items():
        resp = requests.get(server.base_url + "/greeting",
                            headers={"Host": "echo.test"}, timeout=10)
        results[name] = (resp.status_code, resp.content)
    expected = (200, f"{TEMPLATE_GREETING}\n".encode())
    assert results["upstream"] == expected, f"upstream: {results['upstream']!r}"
    assert results["candidate"] == results["upstream"], f"candidate: {results['candidate']!r}"
    up = template_servers["upstream"].startup_lines()
    cand = template_servers["candidate"].startup_lines()
    assert any("envsubst" in line for line in up), "upstream did not run envsubst"
    assert cand == up, "entrypoint output differs:\n" + _diff("\n".join(up), "\n".join(cand))
