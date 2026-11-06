# Engineering notes

Log surprises, failed attempts, and decisions here while working.

## Toolchain

- Development environment: Windows with Ubuntu on WSL 2 and Docker Desktop.
- Trivy 0.76.2 and Grype 0.121.2.

## `set -e` does not protect command substitution

The first version of `scripts/pin-images.sh` pulled images inside a function
called from `$(...)`. Bash ignores `set -e` there, so a failed `docker pull` did
not stop the script. The next command then reported `No such image`, which hid
the real failure.

Fix: pull images before any command substitution, so a failed pull stops the
script straight away. I tested this with a simulated pull failure, and the script
exited without changing `versions.env`.
