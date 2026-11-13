Prefix: PIB
Next: 6

# TODO

PIB-1 through PIB-4 are implemented and verified. The reduced profile is published as an opt-in release and pinned by `usr`; the committed full pin remains the default. See [headless runtime verification](docs/verification/headless-usr.md) for measurements, checks, and remaining limits.

Headless does not mean text-only. Preserve docs, examples, licenses, images, extension loading, detached children, and OpenCode Go's Anthropic, Google, and OpenAI protocols. Any further provider restriction needs an explicit supported-model decision.

### PIB-5 · P4 · Archives carry native prebuilds for other platforms

- **Area:** Build
- **Where:** `tools/archive.py`, `node_modules/@earendil-works/pi-tui/native/*/prebuilds`
- **Problem:** Each archive includes `pi-tui` native prebuilds for other operating systems and architectures. The previously estimated saving is about 0.3 MB; it has not been remeasured for the reduced profile.
- **Recommendation:** First prove that `pi-tui` selects the prebuild by an exact platform path. Then keep the matching prebuild only in `headless-usr`. Remeasure, rerun repeat-build and runtime checks on every target, and exercise both Linux targets under musl before accepting the removal.
- **Effort:** S
