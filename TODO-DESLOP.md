Prefix: DSLP
Next: 9

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1) passed at base `442f463954a6ead8fb9223f8c148bcc4c1bc66cf`. [Verification](AGENTS.md#verification) records the elapsed costs, test boundaries, and artifact checks. The sealed run covered 11 tests. Release artifacts, live providers, and the two-host intercom remain separate checks.

Diagnose (DSLP-2) reviewed first-party `tools/`, packaging metadata, and their tests and docs at `2c6108836ae36c494174e6b76d745f647491df22`. A local companion fixture demonstrated DSLP-6 (P3); the release merge separately checks recorded companion files. The 11-test local baseline passed. No other issue was confirmed within this scope. Release builds, live providers, tailnet operations, upstream sources, and cross-repository behavior were not exercised; review did not establish that those paths are defect-free.

Types (DSLP-3) at `0c5b3c3057e73d89099dc2beea82711b1c8e876b`: ty 0.0.101 reports 10 `missing-type-argument` diagnostics, split into release and vendor boundary work below. `unsound-return-statement`, `unused-ignore-comment`, and Ruff 0.17.4 `ANN401` each report zero. No setting was adopted: the former remains blocked on sound contracts and the others have no qualifying witness. Other candidates remain unmeasured. The Python escape-hatch search in `tools/` and `tests/` found zero matches before and after; no typing changes were made.

Release types (DSLP-7) at base `e28f70241025b396fab6d2fc78a0ee62a1bd71a2`: `uv run --locked ty check --error missing-type-argument tools tests` fell from 10 diagnostics (5 release, 5 vendor) to 5 (all vendor). No checker setting was adopted. A negative checker witness appended temporarily to `tests/release_test.py`, `from tools.release import TargetRecord` followed by `def type_witness(record: TargetRecord) -> None: record["archive"] = 1`, produced exactly one `invalid-assignment` diagnostic under `uv run --locked ty check tests/release_test.py`. The witness was removed after the probe; no ignore was added. Opaque nested input metadata serializes identically on the base and candidate. The sealed numeric archive and product fixtures fail on the base with `unexpected archive name` and pass with explicit identity validation; disabling the target guard makes its fixture fail again. The malformed identity error path changes; supported producer formats and fixture output remain unchanged. Release builds and external installer execution were not run.

Vendor types (DSLP-8) at base `47705f96c6ea84db2492a05856ce2af04afa4a5a`: the five remaining `missing-type-argument` diagnostics fell to zero. All ten original diagnostics concerned unchecked decoded manifest mappings; no false positives were identified. Adopted `missing-type-argument` at error. A bare `dict` return allowed `load()["sources"] = 7` without a diagnostic; the strict rule rejects that bare return annotation. A `Source` witness assigning `7` to `source.files["index.ts"]` now yields one `invalid-assignment`. The sealed numeric revision fixture copied successfully on the base and is rejected before copying now. The minimal fixture and opaque metadata remain supported. Other strict candidates remain unmeasured; `unsound-return-statement`, `unused-ignore-comment`, and `ANN401` each had zero diagnostics and no qualifying witness. No new escape hatches were introduced. No remote update, plan, or live provider work was run.

Tests (DSLP-4, first slice) at base `6bc09103d8914ca4bcd041c308b6ee0e395eda3a`: `make coverage` runs the same 16 sealed Python tests as `make test` and writes `.work/tmp/coverage/coverage.json`. Its seven files equal tracked `tools/*.py`: 255/539 statements and 94/214 branches covered, with 32 partial branches. Archive covers 73/112 statements and 29/44 branches; release 80/104 and 38/56; vendor 102/217 and 27/80. Fetch, intercom, pack, and sizes are unimported and have zero covered statements or branches. This is a component/function layer, not proof of CLI or assembled artifact behavior, and coverage is not a gate. Real intercom and native artifact lanes, boundary gaps, and mutation remain; DSLP-4 stays open.

## Tickets



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






### DSLP-6 · P3 · Companion verification accepts duplicate package kinds

- **Area:** Build verification
- **Where:** tools/verify-companions.mjs:8; Makefile:30; tools/build.sh:109
- **Problem:** The verifier counts three matching filenames but does not require one of each companion or match package names to filenames. A benign local fixture with Claude archives at versions 1.0.0, 1.0.1, and 1.0.2, each containing a matching package.json and valid index.js, makes `node tools/verify-companions.mjs` exit 0 and print three successes while Codex and OpenCode are absent. Stale versioned files can remain in dist because builds copy new archives without clearing that directory. This makes the companion part of make verify misleading; release.py separately checks the provenance companion keys and recorded files, so this reproduction does not establish a published release failure.
- **Recommendation:** Require exactly one archive for each expected companion and verify each package name matches its archive kind; add a local fixture covering duplicates and missing kinds.
- **Fix with:** root-cause
- **Effort:** S

