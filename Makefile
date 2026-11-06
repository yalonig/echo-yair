SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

include versions.env
export

.PHONY: help doctor pin scan-baseline deb image test

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' Makefile

doctor: ## Check the local toolchain
	@bash scripts/doctor.sh

pin: ## Resolve image tags and save their digests
	@bash scripts/pin-images.sh

scan-baseline: ## Scan the pinned upstream image and build the triage table
	@bash scripts/scan.sh "$(UPSTREAM_IMAGE)@$(UPSTREAM_DIGEST)" scans/baseline baseline

deb: ## Build the patched nginx .deb from source in a clean Debian base
	@bash scripts/build-deb.sh

image: ## Build the drop-in container image from the .deb
	@bash scripts/build-image.sh

test: ## Compare the candidate image against upstream (requires: make image)
	@bash scripts/run-tests.sh
