Prefix: DSLP
Next: 9

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1) passed at base `442f463954a6ead8fb9223f8c148bcc4c1bc66cf`. [Verification](AGENTS.md#verification) records the elapsed costs, test boundaries, and artifact checks. The sealed run covered 11 tests. Release artifacts, live providers, and the two-host intercom remain separate checks.

Diagnose (DSLP-2) reviewed first-party `tools/`, packaging metadata, and their tests and docs at `2c6108836ae36c494174e6b76d745f647491df22`. A local companion fixture demonstrated DSLP-6 (P3); the release merge separately checks recorded companion files. The 11-test local baseline passed. No other issue was confirmed within this scope. Release builds, live providers, tailnet operations, upstream sources, and cross-repository behavior were not exercised; review did not establish that those paths are defect-free.

Types (DSLP-3) at `0c5b3c3057e73d89099dc2beea82711b1c8e876b`: ty 0.0.101 reports 10 `missing-type-argument` diagnostics, split into release and vendor boundary work below. `unsound-return-statement`, `unused-ignore-comment`, and Ruff 0.17.4 `ANN401` each report zero. No setting was adopted: the former remains blocked on sound contracts and the others have no qualifying witness. Other candidates remain unmeasured. The Python escape-hatch search in `tools/` and `tests/` found zero matches before and after; no typing changes were made.

Release types (DSLP-7) at base `e28f70241025b396fab6d2fc78a0ee62a1bd71a2`: `uv run --locked ty check --error missing-type-argument tools tests` fell from 10 diagnostics (5 release, 5 vendor) to 5 (all vendor). No checker setting was adopted. A negative checker witness appended temporarily to `tests/release_test.py`, `from tools.release import TargetRecord` followed by `def type_witness(record: TargetRecord) -> None: record["archive"] = 1`, produced exactly one `invalid-assignment` diagnostic under `uv run --locked ty check tests/release_test.py`. The witness was removed after the probe; no ignore was added. Opaque nested input metadata serializes identically on the base and candidate. The sealed numeric archive and product fixtures fail on the base with `unexpected archive name` and pass with explicit identity validation; disabling the target guard makes its fixture fail again. The malformed identity error path changes; supported producer formats and fixture output remain unchanged. Release builds and external installer execution were not run.

## Tickets


### DSLP-3 · P2 · Types: measure and adopt a witnessed strict profile

- **Area:** deslop · types
- **Where:** pyproject.toml; tools/; tests/
- **Problem:** The measured ty missing-type-argument rule reports 10 bare dict uses at unchecked JSON boundaries; unsound-return-statement, unused-ignore-comment and Ruff ANN401 report zero. None has a qualifying defect witness yet, and the remaining strict candidates are unmeasured.
- **Recommendation:** After the release and vendor boundary tickets are resolved, measure remaining candidates and adopt only rules meeting the deslop evidence bar, with a negative checker witness for each; run make test, make lint and the exact checker witnesses.
- **Fix with:** deslop
- **Effort:** M

### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** Coverage and mutation results are unmeasured; no deslop mutation lane exists.
- **Recommendation:** Run the deslop Tests step. Accept: no undispositioned survivor in critical code, the test cost budget holds, and the lane is green where the tools are mirrored.
- **Fix with:** deslop
- **Effort:** L

### DSLP-5 · P2 · Dead code: tools and debloat

- **Area:** deslop · dead code
- **Where:** whole repository
- **Problem:** No dead-code scan has run.
- **Recommendation:** Run the deslop Dead code step. Accept: tools clean or allowlisted with reasons; walk-backs filed as Needs owner tickets.
- **Fix with:** deslop
- **Effort:** M




### DSLP-8 · P2 · Types: establish the vendor manifest contract

- **Area:** deslop · types · vendor
- **Where:** tools/vendor.py:50; tools/build.sh:31; tools/intercom.py:56; tests/vendor_test.py:20
- **Problem:** Five missing-type-argument diagnostics mark vendor functions accepting decoded or caller-provided mappings. load checks only part of the manifest; materialize also accepts a smaller fixture without schema, repository, ref or version. Both build.sh and intercom.py pass json.loads directly, so a full typed manifest would assert unvalidated data.
- **Recommendation:** Establish sound contracts for each consumer without losing accepted inputs or formats, including both materialize callers and the partial fixture; add a negative checker witness. Any malformed-data behavior change needs a sealed fail-before fixture and separate commit. Run make test, make lint and ty with missing-type-argument enabled.
- **Fix with:** typing-audit
- **Effort:** M


### DSLP-6 · P3 · Companion verification accepts duplicate package kinds

- **Area:** Build verification
- **Where:** tools/verify-companions.mjs:8; Makefile:30; tools/build.sh:109
- **Problem:** The verifier counts three matching filenames but does not require one of each companion or match package names to filenames. A benign local fixture with Claude archives at versions 1.0.0, 1.0.1, and 1.0.2, each containing a matching package.json and valid index.js, makes `node tools/verify-companions.mjs` exit 0 and print three successes while Codex and OpenCode are absent. Stale versioned files can remain in dist because builds copy new archives without clearing that directory. This makes the companion part of make verify misleading; release.py separately checks the provenance companion keys and recorded files, so this reproduction does not establish a published release failure.
- **Recommendation:** Require exactly one archive for each expected companion and verify each package name matches its archive kind; add a local fixture covering duplicates and missing kinds.
- **Fix with:** root-cause
- **Effort:** S

