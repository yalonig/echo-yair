SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

include versions.env
export

.PHONY: help doctor pin

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' Makefile

doctor: ## Check the local toolchain
	@bash scripts/doctor.sh

pin: ## Resolve image tags and save their digests
	@bash scripts/pin-images.sh
