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

`make build` uses the committed package locks and local source tarballs. It runs `npm ci` in an isolated work directory. It fails if source tarballs differ from the prepared inputs. `make verify` checks the archive manifest and digest, extracts the archive, starts the CLI, and loads and binds the subagents, intercom, Muse, and Devin extensions. Its Muse fixture confirms that offline startup registers the approved Ember and Spark models without launching `muse` for catalog refresh.

The shipped `pi --help` includes the command reference and examples. The build applies `overlays/pi-cli/help.mjs` to the locked Pi package with `tools/patch-pi-help.mjs`; `make verify` checks the packaged help offline with `tests/pi-help.test.mjs`.

## Devin SWE-2 (experimental)

The MIT-licensed `mizorewww/pi-devin` provider is stored as a source snapshot
(`sources/pi-devin-local`), hashed in `sources/upstreams.json`, and copied
into the runtime after the locked npm install. It has no production npm
packages; the build-time pinned TypeScript compiler emits `.js` modules for
**both** runtime profiles. The official Devin CLI is **not** bundled, and the
provider never obtains credentials during the build. `make verify` injects a
synthetic offline SWE-2 catalog and checks that `devin/swe-2` exposes the
`medium` variant without starting the CLI or making network calls.

On the end-user host, first run `devin auth login` and `devin models list
--format json`. An interactive Pi session should refresh the provider catalog;
scoped workers use `PI_OFFLINE=1` and require the previously populated
`~/.cache/pi-devin/models.json`. Live inference, account usage, token renewal,
and model entitlement cannot be verified by the offline release test. The
adapter speaks an unofficial protocol; pin and re-qualify it on every update.

## Read provenance

Each release has, per target, `pi-<profile>-<version>-<target>.tar.xz` and `pi-<profile>-<version>-<target>.manifest.json` (for example `pi-full-1.5.0-aarch64-apple-darwin.tar.xz`). The manifest records the product, version, target, source revision, `sources.lock.json` digest, archive digest, byte count, and package payload inventory. `SHA256SUMS` covers every other release asset. `provenance.json` records the builder revision, source snapshot digest, target artifact identities, package lock digests, patch digest, builder tool digest, and tool versions.

The Pi CLI and SDK are exact-version precompiled registry packages whose package integrity values are in the npm lock. The intercom core is compiled from its preserved source. The Pi adapters are packed from preserved source snapshots. `patches/muse-offline-catalog.patch` and `patches/muse-host-trust.patch` apply only to the copied Muse source during packaging. `patches/drop-windows.patch` applies to the copied sources after the Intercom patches, stripping Windows-only code paths (named-pipe and loopback TCP transports, the `wscript` broker launcher, `.cmd`/`.bat` shim handling, PowerShell-based process probes and the related docs) from every packed extension; regenerate it by editing the prepared tree (`tools/intercom.py prepare .work/drop-windows/packages`) and diffing against a fresh prepare with `diff -ruN`, rewriting the `---`/`+++` headers to `a/<name>/…`/`b/<name>/…`. `sources/` remains unchanged.

Intercom additionally supports explicitly enrolled coordinator sessions across a
tailnet. The reviewed `intercom-tailnet` patches and administration overlay apply
only to copied sources, with their digest recorded in release provenance. Run
`make test-intercom` for the broker/client protocol checks. See the
[implementation and verification handoff](docs/verification/intercom-tailnet.md)
for configuration, coordinator boundaries, release adoption and two-host checks.

`PROFILE=headless-usr` builds a reduced runtime from the same locked inputs. Packaging compiles the three extensions and Intercom broker with the pinned build-time TypeScript compiler. The archive excludes source maps and type declarations, `tsx`, esbuild, and the AWS/Smithy packages. Bedrock requests return an explicit unsupported-profile error. The full profile retains Bedrock support.

The reduced profile preserves docs, examples, licenses, images, the interactive CLI, and OpenCode Go's Anthropic, Google, and OpenAI protocols. It supplies runtime SDK JavaScript without development declarations. Pi retains `jiti` for user-provided extensions. `headless-usr` describes the intended consumer rather than a dedicated CLI entry point without interactive code.

Build and verify the reduced profile with `make repro verify PROFILE=headless-usr`. `make verify` checks all four OpenCode Go protocols with offline streaming fixtures. For the reduced profile, it also checks Bedrock rejection. `tools/release.py` merges one profile's three target builds into a separate asset directory. The hosted release workflow takes a `profile` choice, `full` by default, and publishes one profile per release. `full` keeps the `release-<sha>` tag; `headless-usr` publishes under `release-headless-usr-<sha>`, so both profiles can be released from one revision.

The `usr` installer accepts an absolute `USR_PI_RUNTIME_PIN` path to a reviewed pin in the existing release-pin format. Without that setting, it uses its committed pin, which is the `headless-usr` prerelease since 2026-11-13; the earlier `full` pin is retrievable from Git history. Selecting a different pin changes the single installed runtime selection, launcher paths, and managed broker configuration. Custom broker commands remain unchanged. A missing selected pin fails installation without falling back to another profile.

The npm 12 builder may require `npm_config_allow_remote=all` when its remote-package policy rejects the locked registry tarball URLs. This setting applies to the build command; scripts remain disabled and npm verifies the committed integrity values. No runtime package installation is required.

Runtime account entitlement and live provider calls require separate verification. A deterministic repeat build proves identical bytes for the tested target and inputs only.

See [headless runtime verification](docs/verification/headless-usr.md) for the size comparison, tested behaviors, and remaining delivery work.
