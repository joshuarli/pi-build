Prefix: PIB
Next: 6

# TODO

PIB-2, PIB-3, and PIB-4 are implemented and verified. PIB-1's builder and installer work is implemented; hosted publication remains open. See [headless runtime verification](docs/verification/headless-usr.md) for measurements, checks, and remaining limits.

Headless does not mean text-only. Preserve docs, examples, licenses, images, extension loading, detached children, and OpenCode Go's Anthropic, Google, and OpenAI protocols. Any further provider restriction needs an explicit supported-model decision.

### PIB-1 · P3 · Hosted releases do not select headless-usr

- **Area:** Release
- **Where:** `.github/workflows/release.yml`, `tools/release.py`, `usr/tools/pi/runtime.pin.json`
- **Problem:** `make build/repro/verify PROFILE=headless-usr` works, the release merger accepts its product identity, and `usr` accepts a reviewed pin through `USR_PI_RUNTIME_PIN`. The hosted workflow still hard-codes `full`, and no reduced-profile release or adoption pin has been published.
- **Recommendation:** Add an explicit workflow profile choice with `full` as the default. Publish one profile per release, with separate tags so both profiles can be released from one revision. Produce a reviewed headless pin only after every target passes. Preserve the committed full pin as the default. Do not point consumers at working-tree verification artifacts.
- **Effort:** S

### PIB-5 · P4 · Archives carry native prebuilds for other platforms

- **Area:** Build
- **Where:** `tools/archive.py`, `node_modules/@earendil-works/pi-tui/native/*/prebuilds`
- **Problem:** Each archive includes `pi-tui` native prebuilds for other operating systems and architectures. The previously estimated saving is about 0.3 MB; it has not been remeasured for the reduced profile.
- **Recommendation:** First prove that `pi-tui` selects the prebuild by an exact platform path. Then keep the matching prebuild only in `headless-usr`. Remeasure, rerun repeat-build and runtime checks on every target, and exercise both Linux targets under musl before accepting the removal.
- **Effort:** S
