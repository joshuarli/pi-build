TARGET ?= aarch64-apple-darwin
PROFILE ?= full
VERSION ?= 1.5.0
NODE ?= node
PYTHON ?= python3.15
PRODUCT := pi-$(PROFILE)
STEM := $(PRODUCT)-$(VERSION)-$(TARGET)
BUILD := .work/build/$(TARGET)/$(PROFILE)
ARTIFACT := dist/$(PROFILE)/$(STEM).tar.xz
MANIFEST := dist/$(PROFILE)/$(STEM).manifest.json
REPRO := .work/repro/$(TARGET)/$(STEM).tar.xz
VERIFY_ROOT := .work/verify/$(TARGET)/$(PROFILE)

.PHONY: prepare build verify repro sizes test lint clean
prepare:
	PREPARE_LOCKS=1 $(NODE) --version
	PREPARE_LOCKS=1 PYTHON="$(PYTHON)" bash tools/build.sh "$(TARGET)" "$(PROFILE)" "$(BUILD)" "$(ARTIFACT)" "$(VERSION)"

build:
	$(NODE) --version
	PYTHON="$(PYTHON)" bash tools/build.sh "$(TARGET)" "$(PROFILE)" "$(BUILD)" "$(ARTIFACT)" "$(VERSION)"

verify:
	$(PYTHON) -I tools/archive.py verify "$(ARTIFACT)" "$(MANIFEST)" "$(TARGET)" "$(PROFILE)" >/dev/null
	$(PYTHON) -c 'from pathlib import Path; import shutil; shutil.rmtree(Path("$(VERIFY_ROOT)"), ignore_errors=True); Path("$(VERIFY_ROOT)").mkdir(parents=True)'
	$(PYTHON) -I tools/archive.py unpack "$(ARTIFACT)" "$(VERIFY_ROOT)"
	$(NODE) "$(VERIFY_ROOT)/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" --version
	TMPDIR="$(CURDIR)/.work/tmp" $(NODE) tools/verify.mjs "$(CURDIR)/$(VERIFY_ROOT)"
	TMPDIR="$(CURDIR)/.work/tmp" $(NODE) tools/verify-providers.mjs "$(CURDIR)/$(VERIFY_ROOT)" "$(PROFILE)"
	TMPDIR="$(CURDIR)/.work/tmp" $(NODE) tools/verify-companions.mjs "$(CURDIR)/dist/$(PROFILE)"

repro: build
	$(NODE) --version
	PYTHON="$(PYTHON)" bash tools/build.sh "$(TARGET)" "$(PROFILE)" ".work/repro/$(TARGET)/$(PROFILE)" "$(REPRO)" "$(VERSION)"
	cmp "$(ARTIFACT)" "$(REPRO)"

sizes:
	$(PYTHON) -I tools/sizes.py "$(PROFILE)"

test:
	mkdir -p .work/tmp
	uv run --locked pytest tests

lint:
	uv run --locked ruff check tools tests
	uv run --locked ty check tools tests

clean:
	rm -rf dist .work .venv .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name node_modules -type d -prune -exec rm -rf {} +
