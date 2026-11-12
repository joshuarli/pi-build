# Build Pi runtime archives

Use the maintainer build to create deterministic, locked Pi runtime archives from this repository's preserved source snapshots.

## Build a native target

The build requires Node.js 26.13.0, npm 12.2.2, Python 3.15.1, and jaq 3.1.2. `sh tools/toolchain.sh TARGET` downloads them under `.work/toolchain/TARGET`, checks each digest in `tools/toolchain.pins`, and prints the bin directory and Python path. Put that directory first on `PATH` and pass `PYTHON=` to `make`. `make prepare TARGET=darwin-arm64 PROFILE=full` downloads production dependencies and writes the target package lock and local source-package tarballs under `locks/`. Run this command only when preparing or intentionally refreshing build inputs.

Build and verify with:

```sh
make build TARGET=darwin-arm64 PROFILE=full
make verify TARGET=darwin-arm64 PROFILE=full
make repro TARGET=darwin-arm64 PROFILE=full
make sizes PROFILE=full
```

The build requires a native runner for `TARGET`. It supports `darwin-arm64`, `linux-x64`, and `linux-arm64`. A successful build on one target says nothing about the others or Linux musl execution. The `Build Pi runtime` workflow runs `prepare` (Linux lock artifacts for review and commit) or `build` (repeat build and verify on each native runner, then CLI and SDK loader checks of the Linux archives under Alpine musl Node).

`make build` uses the committed package locks and local source tarballs. It runs `npm ci` in an isolated work directory. It fails if source tarballs differ from the prepared inputs. `make verify` checks the archive manifest and digest, extracts the archive, starts the CLI, and loads and binds the subagents, intercom, and Muse extensions. Its Muse fixture confirms that offline startup registers the approved Ember and Spark models without launching `muse` for catalog refresh.

## Read provenance

Each archive is `dist/<profile>/<target>-<profile>.tar.gz`. The matching `.manifest.json` records the archive digest, byte count, and package payload inventory. `SHA256SUMS` contains archive digests. `provenance.json` records the builder revision, source snapshot digest, target artifact identities, package lock digests, patch digest, builder tool digest, and tool versions.

The Pi CLI and SDK are exact-version precompiled registry packages whose package integrity values are in the npm lock. The intercom core is compiled from its preserved source. The Pi adapters are packed from preserved source snapshots. `patches/muse-offline-catalog.patch` applies only to the copied Muse source during packaging. `sources/` remains unchanged.

The `full` profile is the only profile currently implemented. Runtime account entitlement, provider calls, Linux targets, and musl execution require separate verification. A deterministic repeat build proves identical bytes for the tested target and inputs only.
