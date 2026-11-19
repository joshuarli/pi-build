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
SIZE_THRESHOLD ?= 5
BASE ?= origin/main
MUTATION_ENGINE_REV := 1497970d9454a6a9875b1f201cbaad71fd92a010
MUTATION_ENGINE := .work/mutation-engine/$(MUTATION_ENGINE_REV).py

.PHONY: prepare build verify repro sizes size-diff test coverage mutants-diff test-companions test-intercom lint clean
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
	uv run --locked $(PYTHON) -I tools/sizes.py "$(PROFILE)"

size-diff:
	uv run --locked $(PYTHON) -I tools/sizes.py "$(PROFILE)" "$(REFERENCE)" --threshold "$(SIZE_THRESHOLD)"

test:
	mkdir -p .work/tmp
	uv run --locked pytest tests

coverage:
	mkdir -p .work/tmp/coverage
	uv run --locked coverage erase
	uv run --locked coverage run -m pytest tests
	uv run --locked coverage combine
	uv run --locked coverage report
	uv run --locked coverage json -o .work/tmp/coverage/coverage.json

$(MUTATION_ENGINE):
	mkdir -p .work/mutation-engine
	git -C .work/mutation-engine init --quiet
	git -C .work/mutation-engine fetch --no-tags --depth=1 https://github.com/laputa-systems/buildlib.git $(MUTATION_ENGINE_REV)
	@output=$$(mktemp "$@.XXXXXX"); trap 'rm -f "$$output"' EXIT; \
		git -C .work/mutation-engine show $(MUTATION_ENGINE_REV):scripts/mutants_gate.py > "$$output" && mv "$$output" "$@"

mutants-diff: $(MUTATION_ENGINE)
	mkdir -p .work/tmp
	TMPDIR="$(CURDIR)/.work/tmp" UV_PROJECT_ENVIRONMENT="$(CURDIR)/.work/mutation-venv" \
		uv run --locked python .github/scripts/python_mutants_gate.py "$(MUTATION_ENGINE)" --base "$(BASE)"

test-companions:
	mkdir -p .work/tmp
	TMPDIR="$(CURDIR)/.work/tmp" $(NODE) --test tests/verify-companions.test.mjs

test-intercom:
	PYTHON="$(PYTHON)" $(NODE) tools/test-intercom.mjs

lint:
	uv run --locked ruff check tools tests .github/scripts/python_mutants_gate.py
	uv run --locked ty check tools tests .github/scripts/python_mutants_gate.py

clean:
	rm -rf dist .work .venv .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name node_modules -type d -prune -exec rm -rf {} +
