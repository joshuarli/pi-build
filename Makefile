TARGET ?= darwin-arm64
PROFILE ?= full
NODE ?= node
PYTHON ?= python3.15
BUILD := .work/build/$(TARGET)/$(PROFILE)
ARTIFACT := dist/$(PROFILE)/$(TARGET)-$(PROFILE).tar.gz
VERIFY_ROOT := .work/verify/$(TARGET)/$(PROFILE)

.PHONY: prepare build verify repro sizes
prepare:
	PREPARE_LOCKS=1 $(NODE) --version
	PREPARE_LOCKS=1 PYTHON="$(PYTHON)" bash tools/build.sh "$(TARGET)" "$(PROFILE)" "$(BUILD)" "$(ARTIFACT)"

build:
	$(NODE) --version
	PYTHON="$(PYTHON)" bash tools/build.sh "$(TARGET)" "$(PROFILE)" "$(BUILD)" "$(ARTIFACT)"

verify:
	$(PYTHON) -I tools/archive.py verify "$(ARTIFACT)" "$(ARTIFACT).manifest.json" "$(TARGET)" "$(PROFILE)" >/dev/null
	$(PYTHON) -c 'from pathlib import Path; import shutil; shutil.rmtree(Path("$(VERIFY_ROOT)"), ignore_errors=True); Path("$(VERIFY_ROOT)").mkdir(parents=True)'
	$(PYTHON) -I tools/archive.py unpack "$(ARTIFACT)" "$(VERIFY_ROOT)"
	$(NODE) "$(VERIFY_ROOT)/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" --version
	TMPDIR="$(CURDIR)/.work/tmp" $(NODE) tools/verify.mjs "$(CURDIR)/$(VERIFY_ROOT)"

repro: build
	$(NODE) --version
	PYTHON="$(PYTHON)" bash tools/build.sh "$(TARGET)" "$(PROFILE)" ".work/repro/$(TARGET)/$(PROFILE)" ".work/repro/$(TARGET)/$(TARGET)-$(PROFILE).tar.gz"
	cmp "$(ARTIFACT)" ".work/repro/$(TARGET)/$(TARGET)-$(PROFILE).tar.gz"

sizes:
	$(PYTHON) -I tools/sizes.py "$(PROFILE)"
