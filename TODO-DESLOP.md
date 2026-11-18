Prefix: DSLP
Next: 7

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1) passed at base `442f463954a6ead8fb9223f8c148bcc4c1bc66cf`. [Verification](AGENTS.md#verification) records the elapsed costs, test boundaries, and artifact checks. The sealed run covered 11 tests. Release artifacts, live providers, and the two-host intercom remain separate checks.

Diagnose (DSLP-2) reviewed first-party `tools/`, packaging metadata, and their tests and docs at `2c6108836ae36c494174e6b76d745f647491df22`. A local companion fixture demonstrated DSLP-6 (P3); the release merge separately checks recorded companion files. The 11-test local baseline passed. No other issue was confirmed within this scope. Release builds, live providers, tailnet operations, upstream sources, and cross-repository behavior were not exercised; review did not establish that those paths are defect-free.

## Tickets


### DSLP-3 · P2 · Types: strict profile and typing findings

- **Area:** deslop · types
- **Where:** type checker and lint configuration; Python/TypeScript sources
- **Problem:** The strict-profile candidates in the deslop skill's tools reference have not been measured here.
- **Recommendation:** Run the deslop Types step. Accept: clean at the adopted profile, escape hatches not increased, witnesses recorded.
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


### DSLP-6 · P3 · Companion verification accepts duplicate package kinds

- **Area:** Build verification
- **Where:** tools/verify-companions.mjs:8; Makefile:30; tools/build.sh:109
- **Problem:** The verifier counts three matching filenames but does not require one of each companion or match package names to filenames. A benign local fixture with Claude archives at versions 1.0.0, 1.0.1, and 1.0.2, each containing a matching package.json and valid index.js, makes `node tools/verify-companions.mjs` exit 0 and print three successes while Codex and OpenCode are absent. Stale versioned files can remain in dist because builds copy new archives without clearing that directory. This makes the companion part of make verify misleading; release.py separately checks the provenance companion keys and recorded files, so this reproduction does not establish a published release failure.
- **Recommendation:** Require exactly one archive for each expected companion and verify each package name matches its archive kind; add a local fixture covering duplicates and missing kinds.
- **Fix with:** root-cause
- **Effort:** S

