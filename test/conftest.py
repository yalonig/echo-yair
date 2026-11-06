"""Boot the upstream and candidate images once per session with identical config
and content, so any response difference is attributable to the image itself."""
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
    def __init__(self, name, cid, base_url):
        self.name = name
        self.cid = cid
        self.base_url = base_url

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
            requests.get(url, timeout=2)
            return
        except requests.exceptions.RequestException as exc:
            last = exc
            time.sleep(0.3)
    raise RuntimeError(f"server not ready at {url}: {last}")


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
            mapping = _docker("port", cid, "80")  # e.g. 127.0.0.1:49153
            port = mapping.splitlines()[0].rsplit(":", 1)[-1]
            base = f"http://127.0.0.1:{port}"
            _wait_ready(base + "/")
            started[name] = Server(name, cid, base)
        yield started
    finally:
        for s in started.values():
            subprocess.run(["docker", "rm", "-f", s.cid], capture_output=True)
