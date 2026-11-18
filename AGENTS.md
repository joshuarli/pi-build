# Pi-build

## Verification

- On macOS ARM64 with Python 3.15.2, `make test` passes 16 sealed tests; `make coverage` runs the same tests with branch coverage and writes `.work/tmp/coverage/coverage.json`.
- On the same host, `make lint` runs Ruff and ty on `tools/` and `tests/` in 0.60 s after test setup and 0.08 s warm. Pull requests run both Make targets through the CI and lint workflows.
- `tests/archive_test.py` exercises archive contents, reproducibility, manifest identity, and path validation for the extracted runtime and `make verify`.
- `tests/release_test.py` checks provenance, checksums, target, and profile identity for the release workflow and usr installer.
- `tests/vendor_test.py` checks snapshot integrity and materialization for `tools/build.sh` and packaging.
- The Python suite calls functions directly. CLI flags and exits, fetch, toolchain setup, packing, building, sizes, intercom overlays, and update/plan commands have no direct tests in that suite.
- The Python coverage report covers all seven tracked `tools/*.py` files, including unimported files. It is informational, not a gate; coverage does not establish assertion strength.
- `make test-intercom` compiles patched sources and exercises the broker and client policy and transport. It can require npm and sockets.
- `make verify` exercises an existing archive, packaged CLI and help, extensions, providers, and companions. `make repro` rebuilds and compares artifacts. See [intercom verification](docs/verification/intercom-tailnet.md) for the two-host procedure.
- The campaign scope covers build and release tooling. It has no identified runtime workload for a performance gate.
- `sources/upstreams.json` lists each bundled tree's repository and revision. `sources.lock.json` records toolchain URLs and digests.
