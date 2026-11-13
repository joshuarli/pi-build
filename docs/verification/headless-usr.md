# Headless runtime verification

These results cover the `headless-usr` packaging changes for Pi 1.5.0, checked on November 13, 2026. The artifacts are working-tree verification builds, not published releases. The installed default remains the committed `full` pin in `usr`.

## Artifact size

The comparison uses the same target lockfiles, source snapshots, pinned tools, and archive compression settings for both profiles. Logical bytes count regular file contents, rather than allocated disk blocks. `make sizes` reads the archive manifests. Each profile was built twice per target and compared byte for byte.

| Target | Full archive bytes | Headless archive bytes | Full logical bytes | Headless logical bytes |
| --- | ---: | ---: | ---: | ---: |
| macOS ARM64 | 20,261,816 | 12,228,732 | 155,660,837 | 79,723,572 |
| Linux ARM64 | 20,127,128 | 12,214,900 | 155,251,679 | 79,551,201 |
| Linux x86-64 | 20,645,564 | 12,215,376 | 155,911,119 | 79,551,197 |

On macOS ARM64, the reduced archive removes 39.6% of compressed bytes and 48.8% of logical bytes. An earlier maps-and-declarations-only experiment produced 16,046,176 compressed bytes and 94,787,593 logical bytes. Compilation and dependency pruning account for the remaining reduction.

These are artifact measurements. Startup latency, extraction time, build-time impact, and resident memory were not measured.

## Packaging policy

The full profile keeps the original runtime packages. The reduced profile applies these changes after the locked install:

- Compile every TypeScript implementation module in subagents, Intercom, and Muse with the existing pinned TypeScript 5.9.3 build dependency. Rewrite package entry points and relative imports to JavaScript. Preserve the source snapshots.
- Point Intercom's broker launch at JavaScript and use native Node arguments by default.
- Replace the unbundled and bundled Bedrock implementations with the same explicit unsupported-profile error.
- Remove `tsx`, esbuild and its native platform package, AWS/Smithy, and their now-unused `@aws/lambda-invoke-store` dependency.
- Exclude maps and declarations when archiving. Derive manifest package sizes from the files actually archived.

Docs, examples, Markdown, licenses, notices, images, and the interactive CLI remain. Pi retains `jiti` for user extensions. The runtime SDK has JavaScript entry points but no development declarations.

OpenCode Go supports Anthropic messages, Google generative AI, OpenAI completions, and OpenAI responses. Its provider name does not justify removing any of those SDK families. Bedrock is the only provider capability intentionally disabled by this change.

## Consumer behavior

`usr` accepts an absolute `USR_PI_RUNTIME_PIN` path. The reviewed pin selects the profile. A missing or invalid selected pin fails installation without falling back to the default.

The generated launcher follows the selected profile. The bridge follows the installed selection's validated receipt, so the installer override need not remain in the bridge process environment. Receipt-derived pins undergo structural and artifact-identity validation. Unsafe selection paths and symlinked receipt locations are rejected.

Broker configuration migrates in both directions. Sync adds `usrBrokerProfile` when it owns the broker command. This distinguishes its native launch from a custom `node` command with empty arguments. Custom commands, custom arguments, confirmation settings, inbound-trigger settings, and unknown fields remain unchanged.

The runtime pointer and broker configuration retain their existing separate atomic writes. A later sync repairs an interrupted managed-configuration migration. This change does not introduce a transaction spanning those two files.

## Checks

Both profiles pass `make repro verify` on these native environments:

| Target | Builder | Repeat-build comparison | Runtime fixtures | Alpine musl fixtures |
| --- | --- | --- | --- | --- |
| macOS ARM64 | Native macOS | Pass | Pass | Not applicable |
| Linux ARM64 | Native ARM64 Docker VM with Ubuntu builder | Pass | Pass | Pass |
| Linux x86-64 | Threadripper with Ubuntu builder | Pass | Pass | Pass |

Builders use Node 26.13.0, npm 12.2.2, Python 3.15.1, and jaq 3.1.2. Linux musl checks use the pinned musl Node and Alpine image from the release workflow. No architecture emulation is used.

The runtime fixtures check CLI version output, all three extensions binding, offline Muse model registration, all four OpenCode Go streaming protocols, SDK RPC with a detached child returning the expected completion, and authorized Intercom messaging in both directions. Intercom confirmation remains enabled and inbound messages do not trigger automatic wakeup. npm and npx traps remain unused.

Reduced-profile checks reject Bedrock through the real lazy SDK streaming API and the bundled implementation. A macOS check with Node source maps enabled confirms that the generated JavaScript stack retains file and line locations without map files. Deliberately changing the compiled Ember output limit makes the extension verifier fail, and restoring the module makes it pass.

The three reduced-profile manifests and archives merge through `tools/release.py`. All generated checksums pass, and the builder-tool digests agree across targets.

`pi-build` tests, ruff, and ty pass. The `usr` checks cover release installation, both broker migrations, custom broker preservation, malformed receipts, pin selection, Muse entry-point resolution, and the Pi, Claude, and OpenCode bridge workers. A real-archive scratch installation passes `full → headless-usr → full`, including cached reselection, launcher execution, broker configuration, and bridge attachment with default-pin loading disabled.

The existing `usr` offline suite passes all 13 cases on rerun. One earlier run failed during Muse fixture cleanup after a successful session start; the isolated case also passed. The compiled Muse host accepts a scoped session start before a turn without creating trust or authentication files. This is local host bootstrap proof, not account entitlement or a live model completion.

The broader `usr` typing check remains red on pre-existing diagnostics. Comparing the same files against their baseline shows no new diagnostics. New profile tests and the changed launcher/configuration module have no typing errors. The existing ty configuration also names a renamed rule.

## Reevaluation

Keep this packaging boundary for now. Every target is about 12.2 MB compressed, and the remaining large packages serve active runtime contracts. On macOS ARM64, coding-agent is 17.4 MB of logical bytes, OpenAI is 7.8 MB, Google is 6.0 MB, subagents is 5.6 MB, and Anthropic is 4.3 MB. Those package totals are not estimates of removable bytes.

The next delivery task is an opt-in hosted release and reviewed consumer pin. Hosted workflows and production pins were not changed in this work. A dedicated headless entry point remains a separate design decision: profile actual startup and module loading before committing to that additional build surface. Native prebuild pruning is a smaller independent follow-up.

Verification artifacts are retained locally under `.work/release-headless`. The native x86-64 verification checkout is parked on threadripper at `/home/josh/repos/pi-build/.work/wt/headless-verify` for artifact review. These paths are scratch, not release inputs.
