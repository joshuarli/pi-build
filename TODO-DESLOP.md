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

Vendor parsing mutation slice at base `052d05ac0884d71bab42a399c7f4a2f83a82cb12`: a sealed copy of `tools/vendor.py` and `tests/vendor_test.py`, Python 3.15.2, mutmut 3.8.1, pytest 9.2.0, and one mutation worker selected only `*parse_sources*`. Both runs selected exactly `tools.vendor.x_parse_sources__mutmut_1` through `_45`; the generated mutated source files compared equal with `cmp` (exit 0). Baseline: 42 killed (IDs 1–11, 13–33, 35–38, 40–45), 3 survived (12, 34, 39), 0 timeout, suspicious, skipped, no tests, or other outcomes. Candidate: all 45 killed, 0 in each other category. The progress denominator 542 is all generated module mutants, not the selected 45. Clean baseline and candidate runs exited 0 in 3.29 s and 4.67 s respectively, under 120 s each; these are run durations, not performance claims.

The three baseline survivors are resolved by observable parsing assertions: 12 replaces the invalid-path error label with `None`; 34 does the same for an invalid file hash; 39 drops the parsed revision when constructing `Source`. The candidate kills each. The fixture has the same path, revision and file-inventory shape as `sources/upstreams.json`; it also retains the existing opaque metadata check. No selected survivor remains. This does not establish mutation adequacy outside this function or close the other DSLP-4 boundaries.

Reproduce from the committed candidate, in a fresh scratch area (the two `git show` commands seal baseline inputs; the candidate uses the checked-out test):

```sh
export TMPDIR="$PWD/.work/tmp" UV_PROJECT_ENVIRONMENT="$PWD/.work/venv" UV_CACHE_DIR="$PWD/.work/tmp/uv-cache"
mkdir -p "$TMPDIR"
for run in baseline candidate; do
  mkdir -p "$TMPDIR/mutation-$run/tools" "$TMPDIR/mutation-$run/tests" "$TMPDIR/mutation-$run/mutants/.work/tmp"
  git show 052d05ac0884d71bab42a399c7f4a2f83a82cb12:tools/vendor.py > "$TMPDIR/mutation-$run/tools/vendor.py"
  cat > "$TMPDIR/mutation-$run/pyproject.toml" <<'EOF'
[tool.mutmut]
source_paths = ["tools/"]
pytest_add_cli_args_test_selection = ["tests/vendor_test.py"]
EOF
done
git show 052d05ac0884d71bab42a399c7f4a2f83a82cb12:tests/vendor_test.py > "$TMPDIR/mutation-baseline/tests/vendor_test.py"
cp tests/vendor_test.py "$TMPDIR/mutation-candidate/tests/vendor_test.py"
for run in baseline candidate; do
  (cd "$TMPDIR/mutation-$run" && /usr/bin/time -p uv run --project ../../.. --frozen --with mutmut==3.8.1 --with pytest==9.2.0 mutmut run --max-children 1 '*parse_sources*')
done
cmp "$TMPDIR/mutation-baseline/mutants/tools/vendor.py" "$TMPDIR/mutation-candidate/mutants/tools/vendor.py"
make test
make lint
```

Use new empty scratch directories for each reproduction. `make test` exited 0 with 17 passed; `make lint` exited 0 with Ruff and ty both passing. This independent injected-defect check exited 1 with `AssertionError: None != 'revision'` at the new revision assertion; it changes only the scratch copy:

```sh
mkdir -p .work/tmp/vendor-defect/tools .work/tmp/vendor-defect/tests
cp tools/vendor.py .work/tmp/vendor-defect/tools/vendor.py
cp tests/vendor_test.py .work/tmp/vendor-defect/tests/vendor_test.py
python3.15 -c 'from pathlib import Path; p=Path(".work/tmp/vendor-defect/tools/vendor.py"); s=p.read_text(); old="sources[name] = Source(path, sha, files, src)"; assert s.count(old) == 1; p.write_text(s.replace(old, "sources[name] = Source(path, None, files, src)"))'
(cd .work/tmp/vendor-defect && uv run --project ../../.. --frozen pytest -p no:cacheprovider tests/vendor_test.py::VendorTests::test_parse_preserves_opaque_manifest_fields)
```

Release merge mutation slice at base `62de40605a700bc356be71eda90c0b1a9a8ce27f`: on Darwin arm64 with Python 3.15.2, mutmut 3.8.1 and pytest 9.2.0, the same full function selection generated 250 `tools.release.x_merge__mutmut_*` identities. Generated mutant files compared equal. The baseline caught 209 and left 41 live. The new fixtures caught 223 and left 27 live. Both runs completed under the 120-second cap with one mutation worker and no other selected outcomes. The 323-identity progress denominator includes other functions.

The added real-asset cases independently reject incorrect archive size and digest, symlinked target archive and manifest, malformed companion records, and a missing companion kind. They catch IDs 108, 110–113, 124, 126, 153, 158, 159, 179, 180, 192 and 193. IDs 2, 3, 4, 13–15, 31, 37, 78, 81, 105, 160, 200, 201, 205, 206, 211, 212, 220, 225, 229, 234, 237, 239, 240, 242 and 250 remain live. The fixture exercises all three configured target triples and `full`; existing tests exercise `headless-usr`. CLI, other functions, and native release execution remain open.

Reproduce in fresh empty scratch directories from this candidate (the baseline is sealed from the base commit):

```sh
export TMPDIR="$PWD/.work/tmp" UV_PROJECT_ENVIRONMENT="$PWD/.work/venv" UV_CACHE_DIR="$PWD/.work/tmp/uv-cache"
mkdir -p "$TMPDIR"
for run in baseline candidate; do
  mkdir -p "$TMPDIR/release-$run/tools" "$TMPDIR/release-$run/tests" "$TMPDIR/release-$run/mutants/.work/tmp"
  git show 62de40605a700bc356be71eda90c0b1a9a8ce27f:tools/release.py > "$TMPDIR/release-$run/tools/release.py"
  printf '[tool.mutmut]\nsource_paths = ["tools/"]\npytest_add_cli_args_test_selection = ["tests/release_test.py"]\n' > "$TMPDIR/release-$run/pyproject.toml"
done
git show 62de40605a700bc356be71eda90c0b1a9a8ce27f:tests/release_test.py > "$TMPDIR/release-baseline/tests/release_test.py"
cp tests/release_test.py "$TMPDIR/release-candidate/tests/release_test.py"
for run in baseline candidate; do
  (cd "$TMPDIR/release-$run" && python3.15 -c 'import os,signal,subprocess,sys,time; t=time.monotonic(); p=subprocess.Popen(["cpu-guard","--cores","2","--","uv","run","--project","../../..","--frozen","--with","mutmut==3.8.1","--with","pytest==9.2.0","mutmut","run","--max-children","1","*x_merge__mutmut_*"],start_new_session=True)
try: code=p.wait(timeout=120)
except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGTERM); p.wait(); code=124
print(f"elapsed={time.monotonic()-t:.2f} exit={code}",flush=True); sys.exit(code)')
done
cmp "$TMPDIR/release-baseline/mutants/tools/release.py" "$TMPDIR/release-candidate/mutants/tools/release.py"
```

An independent fault changed the target archive size comparison to compare the recorded size with itself in a scratch copy. The focused command below exited 1: `ValueError not raised` for the `bytes` subtest. `make test` exited 0 (21 passed); `make lint` exited 0 (Ruff and ty passed).

```sh
mkdir -p "$TMPDIR/release-defect/tools" "$TMPDIR/release-defect/tests"
cp tools/release.py "$TMPDIR/release-defect/tools/release.py"
cp tests/release_test.py "$TMPDIR/release-defect/tests/release_test.py"
python3.15 -c 'from pathlib import Path; p=Path(".work/tmp/release-defect/tools/release.py"); s=p.read_text(); old="archive.stat().st_size != record[\"bytes\"]"; assert s.count(old)==2; p.write_text(s.replace(old,"record[\"bytes\"] != record[\"bytes\"]",1))'
(cd "$TMPDIR/release-defect" && uv run --project ../../.. --frozen pytest -p no:cacheprovider -q tests/release_test.py::ReleaseTests::test_rejects_archive_size_or_digest_mismatch_independently)
make test
make lint
```


The follow-up at `32324e8` uses the same 250 merge identities and the
reproduction above. Normalize the gzip header to `mtime=0` in both fixture
copies before comparing. A clock control at consecutive seconds produced
different companion digests on the old fixture and identical digests with
that change. Without the normalization, two baseline runs counted 224 and
225 catches, with a nominal catch that the standalone control did not repeat.

With deterministic fixtures the baseline caught 223 and the candidate caught
245. The new cases verify provenance diagnostics and the companion archive
name, file type, digest, size, compression and member count. Activating
mutant 212 broke both wrong-size and wrong-digest checks. ID 225 can only alter
an error reached after the archive already passed the basename and regular
file conditions. That path is unreachable for declared bare filenames. IDs
237, 239, 240 and 242 remain open in archive-member validation. All 26 tests,
Ruff and ty passed.


The archive-member follow-up at `55eebda` rejects a rooted name and a parent
component in otherwise sealed companion archives. The verifier only reads
members in this fixture. Changing the requirement from either condition to
both made the two rejections fail. With deterministic fixtures, 249 of the
same 250 merge identities are caught, compared with 245 on the base. ID 225
remains equivalent behind the basename check under the declared inputs.
All 27 tests, Ruff and ty passed. Other release functions, archive tooling and
native qualification remain open.


The release command slice at `d569e29` checks usage status and diagnostics,
a combined or split set of provenance files, and the complete output digest
and checksum inventory. The shape cases reject malformed provenance maps and
all five incorrectly typed target fields. The actual isolated Python script
returned 2 and wrote usage to stderr with no positional arguments. Activating
main ID 1 made the single-file success check fail with status 2.

The full `tools/release.py` module generated the same 323 identities in
independent scratch copies using the established mutmut setup with no selector.
The base caught 287, with 7 live and 29 lacking tests. The candidate caught
321. Merge ID 225 is equivalent for declared archive basenames. Main ID 28
uppercases the provenance filename. The case-sensitive Linux ARM64 trial at
`74c13f1a` caught that identity, giving 322 caught and the same equivalent.
All 31 ordinary tests, Ruff and ty passed.
[Hosted run](https://github.com/joshuarli/pi-build/actions/runs/44309118302)

The archive asset-record slice at base `3b1869d51cddf255a37de7c1ee525ade6b6f31c7` uses Darwin ARM64, Python 3.15.2, mutmut 3.8.1 and pytest 9.2.0. Both sealed runs selected the same 120 identities: `tools.archive.x__inventory__mutmut_1`–`_30`, `x__assemble__mutmut_1`–`_52`, and `x_verify__mutmut_1`–`_38`. The generated mutant sources compare equal. The baseline killed 103 and left 17 live; the candidate killed 116 and left 4 live. There were zero timeouts, suspicious, skipped, no-test or other selected results. Both runs exited 0 in 5.39 seconds, with one worker and a two-core cap; each had a 120-second hard budget.

The new local asset fixture catches inventory and manifest record omissions, nonzero member timestamps, missing parent creation, independent size and digest mismatches, and non-xz input. Baseline survivors caught were assemble IDs 1, 3, 5, 13, 31, 32, 43, 44; verify IDs 19, 29, 30, 31, 35. Remaining inventory ID 5 and assemble IDs 30 and 48 uppercase filesystem paths and survive on this case-insensitive host; they remain open for a case-sensitive native trial. Verify ID 17 alters the identity diagnostic. The exact diagnostic assertion catches that mutation in a separate local run. No accepted risk or equivalent exclusion is claimed for the three platform-dependent cases. Archive validation, unpacking, CLI, other archive decisions, and native artifact qualification remain open; this slice does not close DSLP-4.

Reproduce from the committed candidate in new, empty scratch directories:

```sh
export TMPDIR="$PWD/.work/tmp" UV_PROJECT_ENVIRONMENT="$PWD/.work/venv" UV_CACHE_DIR="$PWD/.work/tmp/uv-cache"
for run in baseline candidate; do
  mkdir -p "$TMPDIR/archive-$run/tools" "$TMPDIR/archive-$run/tests" "$TMPDIR/archive-$run/sources" "$TMPDIR/archive-$run/mutants/sources" "$TMPDIR/archive-$run/mutants/.work/tmp"
  git show 3b1869d51cddf255a37de7c1ee525ade6b6f31c7:tools/archive.py > "$TMPDIR/archive-$run/tools/archive.py"
  printf '{"fixture": "lock"}\n' | tee "$TMPDIR/archive-$run/sources.lock.json" > "$TMPDIR/archive-$run/mutants/sources.lock.json"
  printf '{"fixture": "sources"}\n' | tee "$TMPDIR/archive-$run/sources/upstreams.json" > "$TMPDIR/archive-$run/mutants/sources/upstreams.json"
  printf '[tool.mutmut]\nsource_paths = ["tools/"]\npytest_add_cli_args_test_selection = ["tests/archive_test.py"]\n' > "$TMPDIR/archive-$run/pyproject.toml"
done
git show 3b1869d51cddf255a37de7c1ee525ade6b6f31c7:tests/archive_test.py > "$TMPDIR/archive-baseline/tests/archive_test.py"
cp tests/archive_test.py "$TMPDIR/archive-candidate/tests/archive_test.py"
for run in baseline candidate; do
  (cd "$TMPDIR/archive-$run" && python3.15 -c 'import os,signal,subprocess,sys,time; t=time.monotonic(); p=subprocess.Popen(["cpu-guard","--cores","2","--","uv","run","--project","../../..","--frozen","--with","mutmut==3.8.1","--with","pytest==9.2.0","mutmut","run","--max-children","1","*verify__mutmut_*","*inventory__mutmut_*","*assemble__mutmut_*"],start_new_session=True)
try: code=p.wait(timeout=120)
except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGTERM); p.wait(); code=124
print(f"elapsed={time.monotonic()-t:.2f} exit={code}",flush=True); sys.exit(code)')
done
cmp "$TMPDIR/archive-baseline/mutants/tools/archive.py" "$TMPDIR/archive-candidate/mutants/tools/archive.py"
```

The independent fault below disables the size comparison in a scratch copy. The focused test exits 1 with `ValueError not raised` on the `bytes` subtest. The unmodified full `make test` exits 0 with 32 passed; `make lint` exits 0 with Ruff and ty passing.

```sh
mkdir -p "$TMPDIR/archive-defect/tools" "$TMPDIR/archive-defect/tests" "$TMPDIR/archive-defect/sources" "$TMPDIR/archive-defect/.work/tmp"
cp tools/archive.py "$TMPDIR/archive-defect/tools/archive.py"
cp tests/archive_test.py "$TMPDIR/archive-defect/tests/archive_test.py"
cp "$TMPDIR/archive-baseline/sources.lock.json" "$TMPDIR/archive-defect/sources.lock.json"
cp "$TMPDIR/archive-baseline/sources/upstreams.json" "$TMPDIR/archive-defect/sources/upstreams.json"
python3.15 -c 'from pathlib import Path; p=Path(".work/tmp/archive-defect/tools/archive.py"); s=p.read_text(); old="manifest[\"bytes\"] != Path(archive_path).stat().st_size"; assert s.count(old)==1; p.write_text(s.replace(old, "manifest[\"bytes\"] != manifest[\"bytes\"]"))'
(cd "$TMPDIR/archive-defect" && uv run --project ../../.. --frozen pytest -p no:cacheprovider -q tests/archive_test.py::ArchiveTests::test_real_asset_record_inventory_and_verification)
make test
make lint
```

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

