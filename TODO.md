Prefix: PIB
Next: 6

# TODO

Sizes below were measured on the aarch64-apple-darwin `full` archive from release `full-1.5.0-1` (35.5 MB compressed, about 155 MB of logical file bytes, 208 MB on disk). Before each removal, remeasure with `make sizes`, state the minimum saving and the behaviors that must remain, and rerun `make repro verify` on every target, the musl job, and the `usr` extracted-runtime probes (`test_sdk_protocol.mjs`, `test_intercom_protocol.mjs`, `verify-extensions.mjs`). Names alone (TUI, image, provider) do not prove a module is unreachable. Headless does not mean text-only.

### PIB-1 · P3 · No headless-usr profile can be built or selected

- **Area:** Build
- **Where:** `tools/build.sh:12`, `Makefile`, `tools/release.py`, `.github/workflows/release.yml`, `usr/tools/sync/pi_release.py:57`, `usr/tools/sync/installer.py` (`install_pi`)
- **Problem:** `tools/build.sh` rejects every profile except `full`, and the workflow and release merge assume one profile per release. The `usr` pin schema already accepts `headless-usr`, but the installer has no explicit profile selection, so a reduced closure has no delivery path. Every reduction below depends on this.
- **Recommendation:** Let `build.sh` take a `headless-usr` profile that starts as a copy of `full` and applies an explicit removal list, released as its own product (`pi-headless-usr-<pi version>-<target>`). In `usr`, add an opt-in profile setting that selects a second pin file. Keep `full` as the default and keep bare interactive `pi`. Install exactly one closure.
- **Fix with:** `architect`
- **Effort:** M

### PIB-2 · P3 · Archives ship source maps, type declarations and package docs

- **Area:** Performance
- **Where:** `tools/archive.py:17` (`archive`), `tools/build.sh:99`
- **Problem:** The runtime never reads these files, but they are about 66 MB of the 155 MB logical payload: `.map` 36.1 MB, `.d.ts` 18.9 MB, `.d.mts`/`.d.cts` 5.8 MB, `.md` 5.2 MB. Separately, `pi-coding-agent/docs` and `examples` take 4.3 MB on disk. They inflate download, extraction time and the per-sync inventory hash.
- **Recommendation:** For `headless-usr`, drop `*.map`, `*.d.ts`, `*.d.mts`, `*.d.cts`, and package `docs/` and `examples/` directories while archiving, through a declared, tested exclusion list. Keep `LICENSE`/`NOTICE`/`README` files a license requires. Confirm that no runtime `sourceMappingURL` or `require.resolve` lookup depends on removed files, and that stack traces remain usable without maps.
- **Fix with:** `make-it-fast`
- **Effort:** S

### PIB-3 · P3 · Unused provider SDKs dominate the dependency closure

- **Area:** Dependencies
- **Where:** `tools/build.sh:61` (runtime `package.json`), `locks/*/package-lock.json`
- **Problem:** `usr` routes Pi only through OpenCode Go and the Muse SDK provider. The closure still carries `openai` (28 MB on disk), `@anthropic-ai/sdk` (14 MB), `@google/genai` (11 MB), and `@aws-sdk` plus `@smithy` (15 MB), pulled in through `@earendil-works/pi-ai`. It is `unproven` which ones are loaded lazily and which are imported eagerly. OpenCode Go may use the `openai` client for its OpenAI-compatible API.
- **Recommendation:** Trace the actual imports when the CLI, the SDK session, and a detached child start against the OpenCode Go and Muse fixtures. Remove one provider group per slice with an npm override or a build-time stub, only where unreachable. Each removal must keep the probes green and fail with a clear error if that provider is ever selected.
- **Fix with:** `blast-radius`
- **Effort:** M

### PIB-4 · P4 · TypeScript is compiled at runtime through tsx and esbuild

- **Area:** Performance
- **Where:** `tools/build.sh:74` (`tsx`), `usr/tools/sync/pi_offline.py:102` (launcher `--extension *.ts`), `usr/tools/sync/pi_offline.py:112` (intercom broker loader)
- **Problem:** The launcher loads `pi-subagents` and intercom from `.ts` sources, and the intercom broker runs through `tsx`, so every closure ships `esbuild` (9.7 MB native binary) and transpiles on each start.
- **Recommendation:** Precompile the extension and broker entry points to JS during packaging, and point the `usr` launcher and broker config at the compiled files. Then drop `tsx` from `headless-usr`. Keep the source snapshots unchanged, and keep `usr`'s `configure_intercom` migration in step with the new path.
- **Fix with:** `reference-parity`
- **Effort:** M

### PIB-5 · P4 · Archives carry native prebuilds for other platforms

- **Area:** Build
- **Where:** `tools/archive.py:17`, `node_modules/@earendil-works/pi-tui/native/*/prebuilds`
- **Problem:** Each target archive includes `pi-tui` native prebuilds for every OS and architecture, and darwin includes `fsevents`. The saving is small (about 0.3 MB), but these files are dead weight on each target.
- **Recommendation:** Keep only the prebuild matching the archive target, and only if `pi-tui` loads it by an exact platform path. Do this after PIB-2, using the same exclusion mechanism.
- **Fix with:** `none`
- **Effort:** S
