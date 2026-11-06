SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

include versions.env
export

.PHONY: help doctor pin scan-baseline scan-candidate deb image test all

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-15s %s\n", $$1, $$2}' Makefile

doctor: ## Check the local toolchain
	@bash scripts/doctor.sh

pin: ## Resolve image tags and save their digests
	@bash scripts/pin-images.sh

scan-baseline: ## Scan the pinned upstream image and build the triage table
	@bash scripts/scan.sh "$(UPSTREAM_IMAGE)@$(UPSTREAM_DIGEST)" scans/baseline baseline

scan-candidate: ## Scan the built candidate image and diff it against the baseline
	@bash scripts/scan.sh "echo-nginx:$(NGINX_VERSION)" scans/candidate candidate
	@python3 tools/diff_scans.py --baseline scans/baseline/baseline-triage.csv --candidate scans/candidate/candidate-triage.csv --output scans/candidate/diff.md

deb: ## Build the patched nginx .deb from source in a clean Debian base
	@bash scripts/build-deb.sh

image: ## Build the drop-in container image from the .deb
	@bash scripts/build-image.sh

test: ## Compare the candidate image against upstream (requires: make image)
	@bash scripts/run-tests.sh

all: ## Full pipeline: build the .deb and image, run the tests, rescan and diff
	@$(MAKE) deb
	@$(MAKE) image
	@$(MAKE) test
	@$(MAKE) scan-candidate
