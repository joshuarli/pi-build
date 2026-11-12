# Build Pi runtime archives

Use the maintainer build to create deterministic, locked Pi runtime archives from this repository's preserved source snapshots.

## Build a native target

`TARGET` is a Rust target triple: `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, or `aarch64-unknown-linux-musl`.

The build requires the Node.js, npm, Python, and jaq versions in `bootstrap.lock.json`. `sh tools/toolchain.sh TARGET` downloads them under `.work/toolchain/TARGET`, checks each digest in `sources.lock.json`, and prints the bin directory and Python path. It bootstraps jaq from the same lock when none is on `PATH`. Put that directory first on `PATH` and pass `PYTHON=` to `make`. `make prepare TARGET=aarch64-apple-darwin PROFILE=full` downloads production dependencies and writes the target package lock and local source-package tarballs under `locks/`. Run this command only when preparing or intentionally refreshing build inputs.

Build and verify with:

```sh
make build TARGET=aarch64-apple-darwin PROFILE=full
make verify TARGET=aarch64-apple-darwin PROFILE=full
make repro TARGET=aarch64-apple-darwin PROFILE=full
make sizes PROFILE=full
make test
make lint
make clean
```

The build requires a native runner for `TARGET`. A successful build on one target says nothing about the others. The `Prepare locks` workflow writes Linux lock artifacts for review and commit. The `release` workflow repeats the build and verification on each native runner, runs CLI and SDK loader checks of the Linux archives under Alpine musl Node, and publishes a prerelease. `make lint` runs ruff and ty on `tools/` and `tests/` through `uv`.

`sources.lock.json` pins the toolchain downloads by URL and SHA-256. `bootstrap.lock.json` pins the toolchain versions that `tools/build.sh` asserts and lists the inputs each target installs. npm packages are pinned by the lockfiles under `locks/`, which resolve from the stuff registry (`https://npm.17166969.xyz/current/`) as set in each directory's `.npmrc`.

`make build` uses the committed package locks and local source tarballs. It runs `npm ci` in an isolated work directory. It fails if source tarballs differ from the prepared inputs. `make verify` checks the archive manifest and digest, extracts the archive, starts the CLI, and loads and binds the subagents, intercom, and Muse extensions. Its Muse fixture confirms that offline startup registers the approved Ember and Spark models without launching `muse` for catalog refresh.

## Read provenance

Each release has, per target, `pi-<profile>-<version>-<target>.tar.xz` and `pi-<profile>-<version>-<target>.manifest.json` (for example `pi-full-1.5.0-aarch64-apple-darwin.tar.xz`). The manifest records the product, version, target, source revision, `sources.lock.json` digest, archive digest, byte count, and package payload inventory. `SHA256SUMS` covers every other release asset. `provenance.json` records the builder revision, source snapshot digest, target artifact identities, package lock digests, patch digest, builder tool digest, and tool versions.

The Pi CLI and SDK are exact-version precompiled registry packages whose package integrity values are in the npm lock. The intercom core is compiled from its preserved source. The Pi adapters are packed from preserved source snapshots. `patches/muse-offline-catalog.patch` applies only to the copied Muse source during packaging. `sources/` remains unchanged.

The `full` profile is the only profile currently implemented. Runtime account entitlement, provider calls, Linux targets, and musl execution require separate verification. A deterministic repeat build proves identical bytes for the tested target and inputs only.
