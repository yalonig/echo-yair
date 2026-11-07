#!/usr/bin/env bash
set -euo pipefail

failed=0

check_tool() {
  local tool="$1"
  if command -v "$tool" >/dev/null 2>&1; then
    printf 'OK       %s\n' "$tool"
  else
    printf 'MISSING  %s\n' "$tool"
    failed=1
  fi
}

for tool in git make python3 openssl docker trivy grype; do
  check_tool "$tool"
done

# The tools use Python 3.10+ syntax; check now rather than crash at the first scan.
if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    printf 'OK       python3 >= 3.10 (%s)\n' "$(python3 -c 'import platform; print(platform.python_version())')"
  else
    printf 'OLD      python3 %s (need 3.10+)\n' "$(python3 -c 'import platform; print(platform.python_version())')"
    failed=1
  fi
fi

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    printf 'OK       docker daemon\n'
  else
    printf 'MISSING  docker daemon (start Docker Desktop)\n'
    failed=1
  fi
fi

if grep -q $'\r' Makefile versions.env scripts/*.sh build/*.sh Containerfile; then
  printf 'BAD      CRLF line endings found; re-clone after adding .gitattributes\n'
  failed=1
else
  printf 'OK       LF line endings\n'
fi

# Resources. The full pipeline (6 packages, 2 images, 5 scans) peaks around
# 8 GB of disk and needs a few GB of RAM for the scanners. Running out mid-build
# is not a clean failure (on WSL it can corrupt the distro), so check up front.
need_gb=10; warn_gb=20

free_gb() { df -Pk "$1" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1048576}'; }
check_disk() {  # <path> <label>
  local gb; gb="$(free_gb "$1")"; [ -n "$gb" ] || return 0
  if [ "$gb" -lt "$need_gb" ]; then
    printf 'LOW      disk: %s GB free on %s (need %s GB)\n' "$gb" "$2" "$need_gb"; failed=1
  elif [ "$gb" -lt "$warn_gb" ]; then
    printf 'WARN     disk: %s GB free on %s (%s+ GB recommended)\n' "$gb" "$2" "$warn_gb"
  else
    printf 'OK       disk: %s GB free on %s\n' "$gb" "$2"
  fi
}

check_disk . "the repo filesystem"
# Under WSL + Docker Desktop, Docker's and the distro's virtual disks live on the
# Windows drive and grow until it is full -- that drive is the one that matters.
if grep -qi microsoft /proc/version 2>/dev/null && [ -d /mnt/c ]; then
  check_disk /mnt/c "Windows C: (holds Docker's virtual disk)"
fi

mem_gb="$(awk '/MemTotal/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null)"
if [ -n "$mem_gb" ] && [ "$mem_gb" -lt 4 ]; then
  printf 'WARN     memory: %s GB visible; scanners may fail below ~4 GB\n' "$mem_gb"
elif [ -n "$mem_gb" ]; then
  printf 'OK       memory: %s GB\n' "$mem_gb"
fi

exit "$failed"
