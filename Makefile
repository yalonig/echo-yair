SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

include versions.env
export

.PHONY: help doctor pin scan-baseline scan-candidate pcre2 deb image test selfcheck vex all

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-15s %s\n", $$1, $$2}' Makefile

doctor: ## Check the local toolchain
	@bash scripts/doctor.sh

pin: ## Re-resolve image tags and OVERWRITE the pinned digests (only to move the pins)
	@bash scripts/pin-images.sh

scan-baseline: ## Scan the pinned upstream image and build the triage table
	@bash scripts/scan.sh "$(UPSTREAM_IMAGE)@$(UPSTREAM_DIGEST)" scans/baseline baseline

scan-candidate: ## Scan the built candidate image and diff it against the baseline
	@bash scripts/scan.sh "echo-nginx:$(NGINX_VERSION)" scans/candidate candidate
	@python3 tools/diff_scans.py --baseline scans/baseline/baseline-triage.csv --candidate scans/candidate/candidate-triage.csv \
		--baseline-packages scans/baseline/baseline-packages.txt --candidate-packages scans/candidate/candidate-packages.txt \
		--fail-on-missing --output scans/candidate/diff.md

pcre2: ## Build the version-bumped PCRE2 .deb from Debian source
	@bash scripts/build-pcre2.sh

deb: ## Build the patched nginx .deb + its 4 module .debs from source in a clean Debian base
	@bash scripts/build-deb.sh

image: ## Build the drop-in container image from the .debs
	@bash scripts/build-image.sh

test: ## Compare the candidate image against upstream (requires: make image)
	@bash scripts/run-tests.sh

selfcheck: ## Prove the tests can fail: run them against images that must fail them
	@bash scripts/selfcheck.sh

vex: ## Generate the OpenVEX document and verify it suppresses the backport CVE
	@bash scripts/vex.sh

all: ## Full pipeline: preflight, build all packages + image, test, scan both images (same DB), diff, VEX
	@$(MAKE) doctor
	@$(MAKE) pcre2
	@$(MAKE) deb
	@$(MAKE) image
	@$(MAKE) test
	@$(MAKE) scan-baseline
	@$(MAKE) scan-candidate
	@$(MAKE) vex
