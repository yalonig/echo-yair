"""Image contract: the parts of "drop-in" that no HTTP request can see. The
brief: "Match the upstream image's filesystem layout, user, working directory,
ports, and entrypoint exactly." These compare image metadata (docker inspect)
and the filesystem directly, no server needed.

Allowed differences, and only these:
 - PKG_RELEASE / NJS_RELEASE may carry our +echo1 suffix: they describe the
   installed packages, which are ours.
 - Labels: ours describe our image instead of naming upstream's maintainers.
"""
import difflib
import json
import subprocess

import pytest

from conftest import IMAGES

RELEASE_VARS = {"PKG_RELEASE", "NJS_RELEASE"}
OUR_SUFFIX = "+echo1"
RUNTIME_FIELDS = ["User", "WorkingDir", "Entrypoint", "Cmd", "ExposedPorts", "StopSignal", "Volumes"]

# Everything nginx and the entrypoint own: path, type, mode, owner, symlink target.
# (No timestamps: our packages were built at a different time than upstream's.)
LAYOUT_SCRIPT = (
    "find /etc/nginx /usr/share/nginx /usr/lib/nginx /var/cache/nginx /var/log/nginx "
    "/docker-entrypoint.sh /docker-entrypoint.d /usr/sbin/nginx /usr/bin/njs "
    "-printf '%p %y %m %u:%g %l\\n' 2>&1 | sort"
)
ACCOUNT_SCRIPT = 'grep "^nginx:" /etc/passwd /etc/group'


def _inspect(image):
    out = subprocess.run(["docker", "image", "inspect", image],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)[0]


def _in_image(image, script):
    return subprocess.run(["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", script],
                          check=True, capture_output=True, text=True).stdout


def _diff(a, b):
    return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(),
                                          "upstream", "candidate", lineterm="", n=1))


@pytest.fixture(scope="module")
def inspected():
    return {name: _inspect(image) for name, image in IMAGES.items()}


@pytest.mark.parametrize("field", RUNTIME_FIELDS)
def test_runtime_config_matches(inspected, field):
    up = inspected["upstream"]["Config"].get(field)
    cand = inspected["candidate"]["Config"].get(field)
    assert cand == up, f"{field}: candidate={cand!r} upstream={up!r}"


def test_platform_matches(inspected):
    for key in ("Os", "Architecture"):
        assert inspected["candidate"].get(key) == inspected["upstream"].get(key), key


def test_environment_matches(inspected):
    def env(name):
        return dict(e.split("=", 1) for e in inspected[name]["Config"].get("Env") or [])
    up, cand = env("upstream"), env("candidate")
    assert set(cand) == set(up), (
        f"variables only upstream: {sorted(set(up) - set(cand))}, "
        f"only candidate: {sorted(set(cand) - set(up))}")
    for key, value in up.items():
        allowed = (value, value + OUR_SUFFIX) if key in RELEASE_VARS else (value,)
        assert cand[key] in allowed, f"{key}: candidate={cand[key]!r} upstream={value!r}"


def test_nginx_account_matches():
    up = _in_image(IMAGES["upstream"], ACCOUNT_SCRIPT)
    cand = _in_image(IMAGES["candidate"], ACCOUNT_SCRIPT)
    assert "/etc/passwd:nginx:" in up, f"upstream has no nginx account: {up!r}"
    assert cand == up, _diff(up, cand)


def test_filesystem_layout_matches():
    up = _in_image(IMAGES["upstream"], LAYOUT_SCRIPT)
    cand = _in_image(IMAGES["candidate"], LAYOUT_SCRIPT)
    # Anchor: the listing really covers nginx's tree (and nothing was missing upstream).
    assert "/etc/nginx/nginx.conf f 644 root:root" in up, up[:300]
    assert "No such file" not in up, up
    assert cand == up, "filesystem layout differs:\n" + _diff(up, cand)
