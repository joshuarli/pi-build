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

The new local asset fixture catches inventory and manifest record omissions, nonzero member timestamps, missing parent creation, independent size and digest mismatches, and non-xz input. Baseline survivors caught were assemble IDs 1, 3, 5, 13, 31, 32, 43, 44; verify IDs 19, 29, 30, 31, 35. Inventory ID 5 and assemble IDs 30 and 48 uppercase paths on the case-insensitive host. The case-sensitive Linux ARM64 trial at `4f4efec1` caught all 120 identities after correcting the mutation fixture-directory setup. [Hosted run](https://github.com/joshuarli/pi-build/actions/runs/44312133074) Verify ID 17 alters the identity diagnostic. The exact diagnostic assertion catches that mutation in a separate local run. No accepted risk or equivalent exclusion is claimed for the three platform-dependent cases. Archive validation, unpacking, CLI, other archive decisions, and native artifact qualification remain open; this slice does not close DSLP-4.

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

Extraction tests at `e4c22d212c5663eeb7d9ad64c67ce90b3f19973b`
selected the same 85 validator and unpack identities in fresh macOS seals.
The original tests caught 37, missed 36 and exercised none of the 12 unpack
identities. The candidate caught 73 and missed 12. All 12 unpack identities
were caught. The remaining validator IDs are 30–33, 41, 43, 45–49 and 67.
The production archive code is identical in both seals.

The intended XZ archive is extracted by the real tarfile reader. The test
checks the extracted byte and link inventory and the member selection. The
valid fixture exercises Python's default extraction filter. Invalid metadata stays in in-memory validator fixtures
except for a benign duplicate member that must fail before extraction.
The compression boundary rejects a gzip fixture before creating a destination.
Changing `tarfile.open(source, "r:xz")` to `tarfile.open(source, "r:*")`
in a separate scratch copy made the focused compression test fail with
`ReadError not raised`. All 35 ordinary tests and Ruff and ty passed.

Use the preceding archive mutation recipe with this base and the tracked
`sources.lock.json` and `sources/upstreams.json` in place of the fixture JSON.
Add `also_copy = ["sources.lock.json", "sources/upstreams.json"]` to the
`[tool.mutmut]` config. Select
`tools.archive.x_validate_members__mutmut_*` and
`tools.archive.x_unpack__mutmut_*`, and compare the selected
`exit_code_by_key` maps in `mutants/tools/archive.py.meta`. Both commands
exited zero under the same 120-second bound. Remaining archive validator
identities, vendor, artifact build and live providers remain open.

The pack and size commands were exercised directly through the same
isolated Python entry points as `tools/build.sh` and `make sizes`, from
`cac013c98b251f4b256fa2c32f130bfefec13388`. The pack fixture preserves
regular bytes, permissions, a directory and a relative link. Reversing
input order and changing owners and times yields identical normalized
gzip bytes. Removing the sort in a separate sealed copy makes the test
fail on the byte comparison. The size command prints only the requested
profile, in archive name order, with exact compressed and payload totals.

`tools/pack.py:normalized` had no callers. The tracked references to the
script execute it through `python -I` or include its bytes in the build-tool
digest. The live normalization stays in the member loop. Removing the
unused helper changes the build-tool digest on the next build.
The before and after fixture tests passed. These are CLI checks for the
local package tools. Native builds, providers and broader dead-code work
remain open.

Vendor inventory at `7a8731f07c3cf8b7e0d9dc4d236d7e120bbe1d5d`
selected the same 77 `source_files`, `git_blob_sha` and `load` mutants.
The base caught 16, missed 14 and had 47 without tests. The candidate
caught all 77. Both fresh runs exited zero under 120 seconds, and their
generated production files compared byte for byte. The final witness
accepts mixed-case repository names with the same pinned manifest shape.

The snapshot tests check all three inventory selectors against an
actual tree and reject a symlink in that tree. Git supplies independent
golden digests for the empty, textual and binary blobs. The pinned
manifest fixture tests schema, exact source set, revision, repository
and file inventories. Selecting the general snapshot filter for
Pi-subagents in a disposable source copy made the inventory test fail
on its exact path list.

Use the vendor parsing recipe with this base and fresh before and
candidate copies. Add the tracked `sources/upstreams.json` at
`sources/upstreams.json` to each scratch tree and
`also_copy = ["sources/upstreams.json"]` to the mutmut config, and create
`mutants/sources` and `mutants/.work/tmp` before starting mutmut. Select
`tools.vendor.x_source_files__mutmut_*`, `tools.vendor.x_load__mutmut_*`
and `tools.vendor.x_git_blob_sha__mutmut_*`. Compare the corresponding
`exit_code_by_key` entries in `mutants/tools/vendor.py.meta`.
No upstream update, native build or live provider activity ran.

Archive validation at `8e4bad55de577a49eb58bd013384596056df9f19`
selected the same 85 validator and unpack identities. The base caught
73. The candidate caught 84 in mutmut, including every unpack
identity. Direct member metadata tests check the exact diagnostic
for each link boundary without extracting those fixtures.

The remaining validator ID 67 has an independent local control.
Changing `seen.add(target)` to `seen.add(None)` in a sealed source
copy makes a bounded subprocess test exit 1 with `TimeoutExpired`.
The intact validator reports the cycle from the incoming chain.
Mutmut's parent-process run still reports this identity as surviving
because the isolated subprocess imports a fresh module. Keep the
explicit fault control with the mutation receipt.

Use the prior validator and unpack recipe with this base and the
checked tests. For the independent fault control, copy only
`tools/archive.py` and `tests/archive_test.py` into a new scratch
tree with `.work/tmp`, make the stated edit there, and run
`uv run --project ../../.. --locked pytest -p no:cacheprovider -q tests/archive_test.py::ArchiveTests::test_member_validator_reports_a_chain_leading_into_a_cycle`.
The controlling test timeout is two seconds. No real archive is written
by the cycle test.

Coverage now collects subprocess data with the existing pinned tool.
On the same 40-test suite, this records all 13 pack statements and
seven size statements that were absent from the parent-only report.
With the final 42-test suite, `make coverage` reports 329 of 534
statements and 140 of 214 branches. It erases old data and combines
the parent and subprocess data before writing the JSON report.
Both linters and the scoped fleet policy checks passed.

The fetch command at `70d898577315b500fe4282442faf6cde28244074`
now has tests for invalid arity, empty input requests, nested cache
creation, URL basename selection, ordered output, reuse of good
cached inputs and repair of a corrupt entry. The repair crosses
Buildlib's real checksum and atomic write boundary with a local
response fixture. Disconnecting that handoff in a sealed copy makes
the test fail because the corrupt byte fixture is never repaired.

Both mutation archives generated identical production code for all
44 `fetch.main` identities. The original selection had no test
executing those identities, so mutmut stopped with pending results.
The candidate caught 41. IDs 29 and 36 return the same last slash
segment regardless of how many right splits are allowed. ID 37 uses
index `+1` in place of `-1`; one right split always gives two
segments for a validated HTTPS URL with a host. These three are
equivalent under the input contract.

Use the archive mutation recipe's scratch structure. Copy
`tools/fetch.py`, `tools/pack.py` and `tools/sizes.py` into each
archive. Select `tests/package_tools_test.py` and
`tools.fetch.x_main__mutmut_*` with `only_mutate = ["tools/fetch.py"]`
and `also_copy = ["tools/pack.py", "tools/sizes.py"]`.
Coverage now records all 18 fetch statements and six branches.

The same revision's real fetch command obtained the locked Node
26.13.0 executable archive. The existing local Intercom harness
passed 31 tests with real Unix sockets and zero skips using that
runtime and the pinned compiler lock. In a worktree with a longer
`TMPDIR` prefix, the same fixture failed at Unix socket creation
with `EINVAL`. A short detached checkout at `.work/wt/ic` kept all
scratch inside its `.work/tmp` and restored the pass. The separate
two-host Intercom route remains unverified.

The complete `tools/archive.py` function inventory at
`70d898577315b500fe4282442faf6cde28244074` accounted for 268
identities. Two fresh macOS runs generated the same production
code. The base caught 251 and the candidate caught 258. The
candidate exercises headless symlinks, profile identity, local
staging cleanup and rejection of an unknown profile.

The [case-sensitive Linux trial](https://github.com/joshuarli/pi-build/actions/runs/44324389230)
at `b58334330e367f9e84db02c3f055fb5687c58e14` caught 261 of 268.
It distinguished the three case-only mutations in the node_modules
inventory, sources lock and upstream manifest paths. The committed
source and test files match the trial byte for byte.

The six `x_archive` survivors (14, 16, 18, 19, 23 and 24) change
only names of staging directories within the same parent. None of
those names is stored in the manifest or archive. The packaged file
inventory, link target and cleanup still match the supported contract.
The remaining `x_validate_members__mutmut_67` is covered by the
separate bounded cycle control recorded above. That control covers the
subprocess result outside the parent-process mutation count.

The [trial workflow](https://github.com/joshuarli/pi-build/blob/b58334330e367f9e84db02c3f055fb5687c58e14/.github/workflows/full-archive-mutation-trial.yml)
contains the exact commands and selection. Native build and wider
vendor and gate work remain in DSLP-4.

Intercom overlay helpers at
`992b70926ed50de0a4b9da317edaa57856e9d101` had no prior coverage
in the ordinary Python suite. The new fixtures catch all 88 identities
in `inputs`, `digest` and `apply` with mutmut 3.8.1 and pytest 9.2.0.
They verify ordered patch bytes, the path-bound digest, nested copies,
missing inputs, destination admission and refusal to overwrite a copied
source. Skipping the path component in the digest in a scratch copy
makes the digest test fail on the exact hash. The pinned 31-test
Intercom run above supplies separate real patch and socket evidence.

Reproduce from a scratch tree with `tools/intercom.py`,
`tests/intercom_overlay_test.py`, and `mutants/.work/tmp`.
Set `source_paths = ["tools/"]` and
`pytest_add_cli_args_test_selection = ["tests/intercom_overlay_test.py"]`.
Select `tools.intercom.x_inputs__mutmut_*`,
`tools.intercom.x_digest__mutmut_*`, and
`tools.intercom.x_apply__mutmut_*`. Compare the selected result codes
in `mutants/tools/intercom.py.meta`. The ordinary suite passed and
Ruff and ty passed. Full mutation of prepare and command routing
remains open.

The archive changed-path trial's
[actual PR run](https://github.com/joshuarli/pi-build/actions/runs/44328375342)
at `026813440675ae323d93f3e5e8d43d541b2d8b95` used the event's
base revision. It selected the archive after classifying the three
gate files and passed the 268 identities with the bounded cycle
control. The actual [mixed PR control](https://github.com/joshuarli/pi-build/pull/29)
at `84e04299011828cf332fb401e3abf0fb5fcd9bd4` changed only the
archive source and its test against the trial branch. Both ordinary
checks passed. The
[event gate](https://github.com/joshuarli/pi-build/actions/runs/44328802243/job/134887247586)
checked 269 identities and failed on the removed profile test's
`x_archive__mutmut_6`. The source edit also invalidated the old
survivor hashes. The sealed deletion, mixed, docs-only and unknown
controls passed their expected outcomes. The archive gate remains a
draft while wider scopes and final fleet retention are qualified.

The complete Intercom Python module inventory at
`d0dfb9caa52259981c3e522c49b4ce579d60b03b` selected the same 157
function mutations. The prior suite caught 97, missed 25 and did not
execute 35. The candidate caught 156. The remaining
`x_prepare__mutmut_30` uppercases the manifest path on a casefolding
volume. The intact fixture passed on case-sensitive x86-64 and ARM64
Linux, and the exact uppercase fault failed with `FileNotFoundError`
on both in the [artifact trial](https://github.com/joshuarli/pi-build/actions/runs/44331458109).
The preparation fixtures verify real snapshot copying and stop on an
altered source before calling the patch runner. The CLI checks cover
all three commands, help and the required operation.

Use the preceding Intercom mutation recipe, now copying
`tools/vendor.py` and adding `only_mutate = ["tools/intercom.py"]`
and `also_copy = ["tools/vendor.py"]`. Select `tools.intercom.*`.
The trial's manifest control uses a separate bytecode cache after
changing the filename. All 57 ordinary tests and both linters passed.

Both Pi 1.5.0 artifact profiles built and passed `make verify` on
macOS ARM64 at `992b70926ed50de0a4b9da317edaa57856e9d101`.
The toolchain installation verified Node 26.13.0, npm 12.2.2,
Python 3.15.1 and jaq 3.1.2 from the committed locks. Both archives
passed identity and SHA-256 checks, packaged CLI help, four offline
extensions, four fixture provider interfaces and all three companion
checks. Headless additionally rejects Bedrock explicitly. A separate
headless build ran `tools/build.sh` with a fresh work path and an
output of the same name under `.work/tmp`; `cmp` and SHA-256 matched.
The checkout and committed locks stayed clean.

| Profile | Bytes | SHA-256 |
| --- | ---: | --- |
| Full | 20,821,692 | `4b502f3cd85c294869f0bc5375414cec5bbcc3296ef43953713e522cf129dd6f` |
| Headless | 12,808,876 | `c04d0e08aa7451c3695a0451b27fd9191c966bacf041251fa021557547f8ea3c` |

Reproduce with the output of `sh tools/toolchain.sh aarch64-apple-darwin`
first on `PATH` and the returned Python passed to
`make build verify TARGET=aarch64-apple-darwin PROFILE=<profile> PYTHON=<builder-python>`.
Use the documented npm remote policy for the pinned packages and
leave `PREPARE_LOCKS=0`. Linux artifact and musl-loader results
remain in progress independently. The local checks used fixture
providers and did not publish artifacts or exercise two-host Intercom.

Vendor update publication at `d0dfb9caa52259981c3e522c49b4ce579d60b03b`
reproduced a failed installed-file check after the new manifest and
snapshots had already replaced their originals. The fixture uses two
disposable source directories, stubbed Git calls and real filesystem
renames. A controlled change to the second installed file makes byte
verification fail. Before the repair the changed manifest and both
new snapshots remain. The candidate checks the installed inventory
before replacing the manifest, while backups are still available.
The same verification fault and an interruption during verification
restore the exact original trees and manifest.

The ordinary fixtures cover valid ref choice, preflight checks,
an invalid upstream revision, empty inventory, a failed second
checkout, nested copies, output JSON and both rename failure points.
All 211 final `update` identities were classified with mutmut 3.8.1
and pytest 9.2.0. The suite catches 206. IDs 31, 33, 35 and 36 alter
only the private staging prefix within the same parent and the
temporary tree is removed on every tested outcome. ID 148 uppercases
`package.json` and survives on the casefolding macOS volume. Its
Linux mutation outcome is unmeasured.

Use a fresh scratch directory with `tools/vendor.py`,
`tests/vendor_update_test.py`, and `mutants/.work/tmp`. Set
`source_paths = ["tools/"]` and
`pytest_add_cli_args_test_selection = ["tests/vendor_update_test.py"]`.
Select `tools.vendor.x_update__mutmut_*` with one worker under the
established timeout. The controller operates solely on local
fixtures in this test. Native releases and real upstream updates
are separate from these transactional checks.

On native Linux, both profiles passed `make repro verify` on x86-64 and
ARM64 with the locked builder tools and unchanged locks. All four archives
matched independent rebuilds. Manifest verification, Pi CLI examples, the
offline extension and loopback provider fixtures, and the companion checks
passed. A separate Alpine step reran the CLI and extension checks under
native musl on both targets. The checkout was
`ab29bef46cff931c91c69840e54eb657f2bd7cac`, GitHub's merge of draft head
`d40f7af964aa088308d9b828be8a8717d570d2f3` and base `d0dfb9ca`.
[Hosted Linux run](https://github.com/joshuarli/pi-build/actions/runs/44331458109)

| Linux target | Profile | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| x86_64 musl | headless-usr | 12795700 | `bfa5a51ea28cc0ae2bf313d1d09dfaade18ebe4639f51e99f5e25acda6429b4e` |
| x86_64 musl | full | 21205200 | `69aa0f29d8feb9ba8e3ee06a16489c903ceebe8dbe4ed0bf4607873e2d56403e` |
| aarch64 musl | headless-usr | 12794856 | `40465a3b5e210aa25870de5386870da83451a1bd9298aa46ad222d8cc41e9865` |
| aarch64 musl | full | 20687892 | `750302a9f851abecac1a4ecdbbbd6ee2af360fe47f916cdc1815918a1f15377b` |

The pack and sizes commands now expose their existing bodies to the
fixture through `main()`. The real `python -I` entry points still run in
the ordinary suite. A separate comparison against `fa46069e` produced
identical gzip bytes and stdout for both size profiles. The new dangling
symlink fixture catches pack mutation 55, which attempts to read every
tar member as a file.

With Python 3.15, mutmut 3.8.1 and pytest 9.2.0, the final macOS run caught
83 of 90 identities. Two exact uppercase path faults from sizes, 10 and
22, were caught separately on a case-sensitive Linux container filesystem
using Python 3.14. Pack 13 changes explicit gzip input to autodetection
for already verified gzip companion inputs. Pack 20 and 25 infer the
same write mode from the output stream. Pack 36 and 39 use the default
PAX format. The latter five are equivalent within the builder's input
contract. A non-gzip invocation of `pack.py` is outside that contract.

For the mutation run, copy the three package tools and
`tests/package_tools_test.py` into a fresh scratch directory and create
`mutants/.work/tmp`. Use `source_paths = ["tools/"]`,
`only_mutate = ["tools/pack.py", "tools/sizes.py"]`,
`also_copy = ["tools/fetch.py", "cli-proof/"]`,
`pytest_add_cli_args_test_selection = ["tests/package_tools_test.py"]`
and `use_setproctitle = false`. Copy pristine pack and sizes scripts
into `cli-proof/` and point only the scratch subprocess invocations
there. Isolated subprocesses then use the real CLI without requiring
mutmut while the two direct calls exercise the instrumented bodies.
Use one mutation worker and inspect both `exit_code_by_key` maps.

Companion inventory (DSLP-6) now requires one Claude, one Codex, and
one OpenCode archive and matches each manifest name to its filename.
The fixture with three valid Claude archives and the fixture with a
Codex package named as Claude both exited successfully before this
change. They now exit 1. Missing OpenCode exits 1 before any companion
is accepted. The complete fixture and the actual companion archives in
both macOS profiles pass. Run `make test-companions` for the four fixtures.

The whole vendor controller trial at `334f82f4` generated the same 545
identities before and after the new tests. The generated source files
compared byte for byte. The baseline caught 394 identities, missed 25,
and exercised no test for 126. The new suite caught 537, with eight
survivors and no untested identities or timeouts on macOS. It checks the
CLI's accepted actions, reference validation, help and failures, the
Git command's output and status, the read-only plan, missing and changed
snapshot inventory, and materialization of nested sibling files.

A case-sensitive Linux control using Python 3.14 caught update mutation
148, which changes `package.json` to `PACKAGE.JSON`. In the container's
filesystem, rerun the ordinary successful-update test after changing
that literal and setting a fresh `PYTHONPYCACHEPREFIX`. It raises
`FileNotFoundError` on the changed copy. Seven remaining identities
are equivalent within the supported contract: command 6 and 11 use
the same falsey `check` default, update 31, 33, 35 and 36 change only
the temporary directory prefix, and main 38 splits a supported
`NAME=REF` on its sole equals sign. Multiple equals signs still fail
but can produce different diagnostics.

Use the preceding vendor mutation recipe with both vendor test files,
`also_copy = ["sources/upstreams.json"]` and the entire
`tools.vendor.*` module. Include a pristine `cli-proof/vendor.py` in
the candidate scratch copy and point only the isolated help subprocess
at it. The ordinary tests run the real script and compare its help to
the callable entry point. No upstream network operation ran in these
fixtures. Whole-change and broader first-party shell and JS coverage
remain separate from the Python module proof.

The changed-path Python trial at `5b4ed9807eb92877efc3ad17b218f4b9a2394010`
accounted for all 1,427 identities on Linux ARM64. Mutmut caught 1,404.
The bounded archive cycle fault failed separately and 22 equivalents
matched their recorded source and mutation digests. The mutation and
cycle checks took about 102 seconds from selection to final disposition.
[Hosted full Python run](https://github.com/joshuarli/pi-build/actions/runs/44339905806)

The actual pull-request controls selected zero modules for documentation,
rejected a new unqualified Python path and caught the archive test
deletion when it appeared alone and alongside a sizes source change.
The mixed event completed all 268 archive and 31 sizes identities
before reporting the archive survivor `x_archive__mutmut_6`.
[Documentation](https://github.com/joshuarli/pi-build/actions/runs/44340108850) ·
[Unknown path](https://github.com/joshuarli/pi-build/actions/runs/44340206093) ·
[Deletion](https://github.com/joshuarli/pi-build/actions/runs/44340262550) ·
[Mixed change](https://github.com/joshuarli/pi-build/actions/runs/44340128560)

`make mutants-diff BASE=<commit>` is the normal entry point. It uses
the mirrored, locked mutmut and the pinned Buildlib diff and result
readers. Run on a case-sensitive filesystem. The gate runs complete
named Python modules and selects their dependent modules and tests.
Changes to the build tools, workflow, locks and overlays select all
seven modules. Native profile, companion and Intercom checks exercise
the corresponding runtime behavior.

The cumulative review at `0da2614b` reproduced three interrupted vendor
transactions. An interruption after moving the first original snapshot
removed it, an interruption after replacing the manifest restored the
old source files under a new manifest, and a failed restore deleted
the only backups. These were simulated after real renames in scratch
directories with fake Git responses.

The update now records the intended backup paths before moving the
originals. It stages the manifest in a unique temporary directory,
then distinguishes interruption before and after the atomic rename by
whether the proposed file still exists. An interrupted restore leaves
the original bytes under `sources/.pi-backup-*/` for recovery. Run
`make test` for all three regressions and the unchanged packing checks.

The new vendor source generated 552 identities. The macOS run caught
543. Case-sensitive Linux caught update 148 (uppercase `package.json`)
and 183 (uppercase backup parent path) with the successful update
fixture and fresh bytecode prefixes. The remaining seven equivalents
are unchanged in behavior and bound to the new source and spans.

## Tickets



### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** The two-host Intercom qualification and final checked-head test-cost comparison remain open.
- **Recommendation:** Verify the retained Python mutation gate and run the two-host procedure in `docs/verification/intercom-tailnet.md`.
- **Fix with:** deslop
- **Effort:** L

### DSLP-5 · P2 · Dead code: tools and debloat

- **Area:** deslop · dead code
- **Where:** whole repository
- **Problem:** No dead-code scan has run.
- **Recommendation:** Run the deslop Dead code step. Accept: tools clean or allowlisted with reasons; walk-backs filed as Needs owner tickets.
- **Fix with:** deslop
- **Effort:** M
