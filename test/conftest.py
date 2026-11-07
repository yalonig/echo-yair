"""Boot the upstream and candidate images with identical config and content, so
any response difference is attributable to the image itself.

Session fixtures (each boots one container per image):
  servers           -- base config (fixtures/nginx.conf) for compat_test.py.
  ext_servers       -- extended config (fixtures/nginx-ext.conf): all six module
                       objects loaded, a TLS listener; for module_tls_test.py.
  default_servers   -- NO mounts at all: the image exactly as `docker run` gives
                       it, with its packaged config and entrypoint; for
                       default_test.py.
  template_servers  -- no config mount, only an /etc/nginx/templates dir and an
                       env var, exercising the entrypoint's envsubst feature.
Kept separate so a problem in one setup can only fail its own tests.
"""
import contextlib
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
        out = subprocess.run(["docker", "logs", self.cid], capture_output=True, text=True)
        return out.stdout + out.stderr

    def startup_lines(self):
        """The entrypoint's own output: stdout up to and including its
        'ready for start up' line (later stdout is the access log)."""
        out = subprocess.run(["docker", "logs", self.cid], capture_output=True, text=True)
        lines = []
        for line in out.stdout.splitlines():
            lines.append(line)
            if "ready for start up" in line:
                break
        return lines

    def exec(self, *cmd):
        return subprocess.run(
            ["docker", "exec", self.cid, *cmd], check=True, capture_output=True, text=True
        )


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


def _start(name, image, *, mounts=(), env=None, https=False, ready_path="/"):
    args = ["run", "-d", "--rm", "-p", "127.0.0.1::80"]
    if https:
        args += ["-p", "127.0.0.1::443"]
    for src, dst in mounts:
        args += ["-v", f"{src}:{dst}:ro"]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    cid = _docker(*args, image)
    try:
        base = f"http://127.0.0.1:{_mapped_port(cid, 80)}"
        https_url = f"https://127.0.0.1:{_mapped_port(cid, 443)}" if https else None
        _wait_ready(base + ready_path)
    except Exception:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)  # never leak
        raise
    return Server(name, cid, base, https_url)


@contextlib.contextmanager
def _pair(**kwargs):
    started = {}
    try:
        for name, image in IMAGES.items():
            started[name] = _start(name, image, **kwargs)
        yield started
    finally:
        for s in started.values():
            subprocess.run(["docker", "rm", "-f", s.cid], capture_output=True)


def _self_signed_cert(dest_dir):
    """A throwaway self-signed cert so the TLS listener can start. Generated at
    runtime rather than committed, to avoid shipping a private key in the repo."""
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(dest_dir / "test.key"), "-out", str(dest_dir / "test.crt"),
         "-days", "1", "-subj", "/CN=localhost"],
        check=True, capture_output=True,
    )


@pytest.fixture(scope="session")
def servers():
    with _pair(mounts=[(FIXTURES / "nginx.conf", "/etc/nginx/nginx.conf"),
                       (FIXTURES / "srv", "/srv")]) as started:
        yield started


@pytest.fixture(scope="session")
def ext_servers(tmp_path_factory):
    certs = tmp_path_factory.mktemp("certs")
    _self_signed_cert(certs)
    with _pair(mounts=[(FIXTURES / "nginx-ext.conf", "/etc/nginx/nginx.conf"),
                       (FIXTURES / "srv", "/srv"),
                       (certs, "/etc/nginx/certs")],
               https=True, ready_path="/njs") as started:
        yield started


@pytest.fixture(scope="session")
def default_servers():
    with _pair() as started:  # out of the box: no mounts, no env
        yield started


TEMPLATE_GREETING = "hello-from-envsubst"


@pytest.fixture(scope="session")
def template_servers():
    with _pair(mounts=[(FIXTURES / "templates", "/etc/nginx/templates")],
               env={"ECHO_GREETING": TEMPLATE_GREETING}) as started:
        yield started
