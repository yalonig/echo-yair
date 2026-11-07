"""Boot the upstream and candidate images with identical config and content, so
any response difference is attributable to the image itself.

Two session fixtures:
  servers      -- the base config (fixtures/nginx.conf), used by the parity and
                  CVE suite in compat_test.py.
  ext_servers  -- an extended config (fixtures/nginx-ext.conf) that loads the
                  njs and image-filter dynamic modules and adds a TLS listener,
                  used by module_tls_test.py. Kept separate so a problem in the
                  richer config can only fail those tests, not the whole suite.
"""
import os
import pathlib
import subprocess
import time

import pytest
import requests

HERE = pathlib.Path(__file__).parent
FIXTURES = HERE / "fixtures"

IMAGES = {
    "upstream": os.environ.get("UPSTREAM_IMAGE", "nginx:1.25-bookworm"),
    "candidate": os.environ.get("CANDIDATE_IMAGE", "echo-nginx:1.25.5"),
}


def _docker(*args):
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class Server:
    def __init__(self, name, cid, base_url, https_url=None):
        self.name = name
        self.cid = cid
        self.base_url = base_url
        self.https_url = https_url

    def logs(self):
        out = subprocess.run(
            ["docker", "logs", self.cid], capture_output=True, text=True
        )
        return out.stdout + out.stderr


def _wait_ready(url, timeout=25):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            requests.get(url, timeout=2, verify=False)
            return
        except requests.exceptions.RequestException as exc:
            last = exc
            time.sleep(0.3)
    raise RuntimeError(f"server not ready at {url}: {last}")


def _mapped_port(cid, container_port):
    mapping = _docker("port", cid, str(container_port))  # e.g. 127.0.0.1:49153
    return mapping.splitlines()[0].rsplit(":", 1)[-1]


@pytest.fixture(scope="session")
def servers():
    conf = str(FIXTURES / "nginx.conf")
    srv = str(FIXTURES / "srv")
    started = {}
    try:
        for name, image in IMAGES.items():
            cid = _docker(
                "run", "-d", "--rm",
                "-p", "127.0.0.1::80",
                "-v", f"{conf}:/etc/nginx/nginx.conf:ro",
                "-v", f"{srv}:/srv:ro",
                image,
            )
            base = f"http://127.0.0.1:{_mapped_port(cid, 80)}"
            _wait_ready(base + "/")
            started[name] = Server(name, cid, base)
        yield started
    finally:
        for s in started.values():
            subprocess.run(["docker", "rm", "-f", s.cid], capture_output=True)


def _self_signed_cert(dest_dir):
    """A throwaway self-signed cert so the TLS listener can start. Generated at
    runtime rather than committed, to avoid shipping a private key in the repo."""
    crt = dest_dir / "test.crt"
    key = dest_dir / "test.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(crt),
         "-days", "1", "-subj", "/CN=localhost"],
        check=True, capture_output=True,
    )


@pytest.fixture(scope="session")
def ext_servers(tmp_path_factory):
    conf = str(FIXTURES / "nginx-ext.conf")
    srv = str(FIXTURES / "srv")
    certs = tmp_path_factory.mktemp("certs")
    _self_signed_cert(certs)
    started = {}
    try:
        for name, image in IMAGES.items():
            cid = _docker(
                "run", "-d", "--rm",
                "-p", "127.0.0.1::80",
                "-p", "127.0.0.1::443",
                "-v", f"{conf}:/etc/nginx/nginx.conf:ro",
                "-v", f"{srv}:/srv:ro",
                "-v", f"{certs}:/etc/nginx/certs:ro",
                image,
            )
            base = f"http://127.0.0.1:{_mapped_port(cid, 80)}"
            https = f"https://127.0.0.1:{_mapped_port(cid, 443)}"
            _wait_ready(base + "/njs")
            started[name] = Server(name, cid, base, https_url=https)
        yield started
    finally:
        for s in started.values():
            subprocess.run(["docker", "rm", "-f", s.cid], capture_output=True)
