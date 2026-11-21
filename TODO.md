Prefix: PIB
Next: 10

# TODO

PIB-1 through PIB-4 are implemented and verified. The reduced profile is published as an opt-in release and pinned by `usr`; the committed full pin remains the default. See [headless runtime verification](docs/verification/headless-usr.md) for measurements, checks, and remaining limits.

Headless does not mean text-only. Preserve docs, examples, licenses, images, extension loading, detached children, and OpenCode Go's Anthropic, Google, and OpenAI protocols. Any further provider restriction needs an explicit supported-model decision.

### PIB-7 · P2 · Verify Intercom across two enrolled hosts

- **Area:** Needs owner · Intercom environment
- **Where:** docs/verification/intercom-tailnet.md, Actual tailnet and harness acceptance
- **Problem:** Local real sockets, offline provider fixtures and native artifact checks have passed. No result records two separately enrolled tailnet hosts with the actual coordinator harnesses, so cross-host delivery and credential recovery are still unproven.
- **Recommendation:** Use the documented disposable enrollments on two available tailnet hosts. Run bidirectional delivery through the named harnesses, identity recovery, fleet isolation, revocation and worker isolation. Record the checked builder revision and each host and harness pair.
- **Fix with:** none
- **Effort:** M

### PIB-9 · P2 · A running coordinator cannot be reached from another host without relaunching it

- **Area:** Intercom
- **Where:** agent-intercom-claude claude-server (spawnBrokerIfNeeded, lazy getClient reconnect); broker/tailnet-admin.ts; usr intercom-tailnet run; docs/verification/intercom-tailnet.md
- **Problem:** On 2026-11-21 a Claude coordinator on the Mac needed to message a long-running Claude session on threadripper (started 15 h earlier as plain `claude` in tmux). There was no path: (1) the tailnet hub on threadripper (tcp://100.98.145.91:47831) admits only coordinators launched through `intercom-tailnet run --endpoint ... --credential ... -- claude`; `intercom-tailnet inspect` listed only `mac/main`, not connected, and neither live session was enrolled, so both would have to be restarted, losing their context. (2) threadripper's machine broker (~/.pi/agent/intercom/broker.sock) was not running; the session's claude-server.mjs (alive for 16 h) only reconnects lazily on its own next intercom tool call, so a one-shot MCP client on the same host saw `No intercom sessions connected.` (3) Separately, `node .../agent-intercom-claude/dist/cci.mjs --help` started an intercom worker (`claude-josh-worktree-...`) and wrote claude-worker-mcp-*.json instead of printing help.
- **Recommendation:** Let an already-running coordinator join a fleet without a restart, for example an MCP tool or command that loads an enrollment credential into the live claude-server and switches it to the remote endpoint, preserving the no-local-fallback rule. Keep a registered presence while the session is idle (eager connect or a heartbeat) so peers can discover it, with inboundTrigger still never by default. Make cci --help print usage without side effects. Acceptance: from the Mac, a coordinator discovers and delivers a message to a Claude session on threadripper that was started before enrollment, without restarting it; `cci --help` exits 0 printing help and creates no files or processes.
- **Fix with:** none
- **Effort:** M

### PIB-8 · P3 · Measure build and runtime wait times

- **Area:** Build and runtime performance
- **Where:** Makefile build and verify targets; docs/verification/headless-usr.md
- **Problem:** Unproven: build duration, extraction time, startup latency and runtime memory have no representative performance workload or regression comparison. A user-visible slowdown can ship while correctness checks pass.
- **Recommendation:** Define representative build, extraction and packaged startup journeys with correctness checks, capture resource use, and compare repeated baseline and candidate runs on a gated host. Start attribution with process-tree CPU sampling and peak memory measurement.
- **Fix with:** bench-pyramid
- **Effort:** L

### PIB-5 · P4 · Archives carry native prebuilds for other platforms

- **Area:** Build
- **Where:** `tools/archive.py`, `node_modules/@earendil-works/pi-tui/native/*/prebuilds`
- **Problem:** Each archive includes `pi-tui` native prebuilds for other operating systems and architectures. The previously estimated saving is about 0.3 MB; it has not been remeasured for the reduced profile.
- **Recommendation:** First prove that `pi-tui` selects the prebuild by an exact platform path. Then keep the matching prebuild only in `headless-usr`. Remeasure, rerun repeat-build and runtime checks on every target, and exercise both Linux targets under musl before accepting the removal.
- **Fix with:** Remeasured archive sizes plus passing repeat-build, runtime and musl checks on all three targets with only the matching prebuild retained.
- **Effort:** S

### PIB-6 · P4 · Headless runtime warns about a missing pi-subagents CHANGELOG on startup

- **Area:** Build
- **Where:** `tools/headless.mjs`, `node_modules/pi-subagents` upgrade notice
- **Problem:** Interactive Pi from release-headless-usr-f6fc723 prints `Failed to show the pi-subagents upgrade notice: ENOENT ... node_modules/pi-subagents/CHANGELOG.md` over the TUI on startup (observed on macOS arm64 2026-11-14); the archive omits the file the notice reads, and the error text corrupts the footer that UI automation reads.
- **Recommendation:** Either ship pi-subagents' CHANGELOG.md in headless-usr or patch the notice to skip a missing changelog; add a verify.mjs check that the extracted runtime starts without that error.
- **Fix with:** A headless extraction check that launches the TUI and asserts no upgrade-notice error
- **Effort:** S

