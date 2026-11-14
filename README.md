# Build Pi runtime archives

Use the maintainer build to create deterministic, locked Pi runtime archives from this repository's preserved source snapshots.

## Build a native target

`TARGET` is a Rust target triple: `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, or `aarch64-unknown-linux-musl`.

The build requires the Node.js, npm, Python, and jaq versions in `bootstrap.lock.json`. `sh tools/toolchain.sh TARGET` downloads them under `.work/toolchain/TARGET`, verifies each pinned input with `laputa-buildlib` (hash-pinned in `sources.lock.json` and installed into the builder Python), and prints the bin directory and Python path. It bootstraps jaq from the same lock when none is on `PATH`. Put that directory first on `PATH` and pass `PYTHON=` to `make`. `make prepare TARGET=aarch64-apple-darwin PROFILE=full` downloads production dependencies and writes the target package lock and local source-package tarballs under `locks/`. Run this command only when preparing or intentionally refreshing build inputs.

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

The Pi CLI and SDK are exact-version precompiled registry packages whose package integrity values are in the npm lock. The intercom core is compiled from its preserved source. The Pi adapters are packed from preserved source snapshots. `patches/muse-offline-catalog.patch` and `patches/muse-host-trust.patch` apply only to the copied Muse source during packaging. `sources/` remains unchanged.

`PROFILE=headless-usr` builds a reduced runtime from the same locked inputs. Packaging compiles the three extensions and Intercom broker with the pinned build-time TypeScript compiler. The archive excludes source maps and type declarations, `tsx`, esbuild, and the AWS/Smithy packages. Bedrock requests return an explicit unsupported-profile error. The full profile retains Bedrock support.

The reduced profile preserves docs, examples, licenses, images, the interactive CLI, and OpenCode Go's Anthropic, Google, and OpenAI protocols. It supplies runtime SDK JavaScript without development declarations. Pi retains `jiti` for user-provided extensions. `headless-usr` describes the intended consumer rather than a dedicated CLI entry point without interactive code.

Build and verify the reduced profile with `make repro verify PROFILE=headless-usr`. `make verify` checks all four OpenCode Go protocols with offline streaming fixtures. For the reduced profile, it also checks Bedrock rejection. `tools/release.py` merges one profile's three target builds into a separate asset directory. The hosted release workflow takes a `profile` choice, `full` by default, and publishes one profile per release. `full` keeps the `release-<sha>` tag; `headless-usr` publishes under `release-headless-usr-<sha>`, so both profiles can be released from one revision.

The `usr` installer accepts an absolute `USR_PI_RUNTIME_PIN` path to a reviewed pin in the existing release-pin format. Without that setting, it uses its committed pin, which is the `headless-usr` prerelease since 2026-11-13; the earlier `full` pin is retrievable from Git history. Selecting a different pin changes the single installed runtime selection, launcher paths, and managed broker configuration. Custom broker commands remain unchanged. A missing selected pin fails installation without falling back to another profile.

The npm 12 builder may require `npm_config_allow_remote=all` when its remote-package policy rejects the locked registry tarball URLs. This setting applies to the build command; scripts remain disabled and npm verifies the committed integrity values. No runtime package installation is required.

Runtime account entitlement and live provider calls require separate verification. A deterministic repeat build proves identical bytes for the tested target and inputs only.

See [headless runtime verification](docs/verification/headless-usr.md) for the size comparison, tested behaviors, and remaining delivery work.
