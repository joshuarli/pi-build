# Tailnet coordinator Intercom: implementation and verification handoff

## Delivery state

The source implementation and locked source packages add explicit remote
connections for Pi, Claude Code, Codex and OpenCode coordinators. The canonical
hub is the patched Pi broker. The `usr` launcher and deployment instructions are
in [usr's tailnet guide](https://github.com/joshuarli/usr/blob/main/docs/intercom-tailnet.md).

This change does not activate a listener on any machine. A native build and
release, adoption of its actual asset digests in `usr`, and real two-host harness
verification remain required. The previous `usr` release pin stays valid until
that release exists. Do not invent a pin or replace installed files manually.

## Implemented contract

- `AGENT_INTERCOM_REMOTE_ENDPOINT` selects a remote broker explicitly. It accepts
  `tcp://<literal-tailnet-IP>:<port>` or `unix:///absolute/forwarded.sock`.
- TCP addresses must be in `100.64.0.0/10` or `fd7a:115c:a1e0::/48`. Wildcards,
  public addresses, loopback TCP, DNS names and URL credentials are rejected.
  Deployment must still confirm that the address belongs to the intended
  Tailscale interface and that tailnet policy permits the connection.
- `AGENT_INTERCOM_ACCESS_CREDENTIAL_PATH` names a private per-coordinator
  enrollment or session credential. The endpoint and credential must be supplied
  together. Remote failures never trigger local auto-spawn or local fallback.
- `AGENT_INTERCOM_REMOTE_LISTEN` enables a persistent hub listener in the Pi
  broker. It accepts the same address grammar. Connections through that listener
  and `remote-gateway.sock` receive remote authentication and policy enforcement.
  The separate local `broker.sock` remains the administration endpoint.
- `broker/tailnet-admin.ts` (compiled to `.js` in `headless-usr`) issues enrollment,
  inspects fleets without secrets, and revokes sessions. It always contacts the
  local administration socket. Enrollment files are exclusively created at mode
  `0600`; their secrets are never printed.
- `remote-fleet` principals may discover, send, ask and reply to coordinators in
  their own fleet. They cannot discover unrelated local sessions, cross fleets,
  delegate children, or invoke administration. Broker-owned identities use
  `HOST/NAME` and a stable issued session ID.
- Existing `remote-tree` policy remains separate. Policy/vector semantics are
  version 3, with a matching hash negotiated by all patched clients. Registry v3
  imports prior v1/v2 tree records; older brokers cannot read the new registry.
- Pi's extension refuses native/scoped child contexts before registering tools or
  handlers. `usr` strips coordinator Intercom variables from SDK and CLI worker
  launches and keeps its SDK extension allowlist closed. This is a capability
  boundary within the harnesses, not isolation from arbitrary same-user code.

Use a dedicated hub state directory, as the `usr` launcher does. Ordinary local
companion brokers are still local adapters; they must not own the hub registry.
The dormant protected-provider/Boss migration contract is not enabled by this
change and does not yet migrate v3 fleet grants.

## Source and build ownership

Preserved `sources/` inventories remain byte-for-byte upstream snapshots.
`tools/intercom.py` applies the reviewed policy and transport patches to the
verified copied packages and adds the administration overlay. Native packaging
and the protocol tests use the same inputs. Release provenance includes the
combined Intercom patch/overlay digest.

All four clients use the same compiled shared-core policy. Claude/Codex inline it
in their esbuild bundles; OpenCode vendors it. A release must update the Pi
runtime and all companion assets together. Do not combine an updated Pi runtime
with stale companion packages.

The changed core/Pi tarballs and companion tarballs are committed under `locks/`,
and all three runtime package locks carry their new integrity values. During
implementation the available TypeScript 5.9.3 and esbuild 0.28.1 first reproduced
the old compiled outputs and normalized source-package archives byte-for-byte.
Those same tools regenerated the changed locked inputs. This is useful package
evidence; it does not replace the pinned native toolchain/reproducibility gate.

## Checks completed in the implementation environment

The executor disallows Unix-socket bind/connect. The explicit command below
substitutes duplex streams only at the transport boundary and skips the separate
OS-socket administration smoke:

```sh
INTERCOM_TEST_NO_SOCKETS=1 make test-intercom PYTHON=python3
```

The tests exercise the actual broker, registry, authorization, framing and all
four client classes: enrollment, host-qualified identity, discovery,
acknowledged messages, stable reconnect, incompatible policy rejection,
credential permissions, revocation/expiry, fleet isolation, no local fallback,
and child exclusion. They also check that an explicitly enabled hub survives the
ordinary idle timeout. No model account, live agent message, or Tailscale host is
used. TypeScript checking of the changed core/broker/CLI paths and source
inventory checks were also performed.

## Native build and release gate

1. Check out the final implementation revision, install the pinned toolchain
   through the existing builder procedure, and run on a host with Unix sockets:

   ```sh
   make test-intercom PYTHON="$PYTHON"
   make repro verify TARGET=x86_64-unknown-linux-musl PROFILE=headless-usr PYTHON="$PYTHON"
   ```

   Do not set `INTERCOM_TEST_NO_SOCKETS` for acceptance. The default tests require
   real sockets. The hosted release workflow runs them before native builds.

2. Repeat the native archive/reproducibility checks for macOS ARM64 and Linux
   ARM64; run the existing Alpine musl checks. Confirm that locked source
   tarballs reproduce without modification. If a mismatch occurs, inspect it
   before refreshing locks; do not bypass the comparison.

3. Check the extracted `headless-usr` administration entrypoint with `--help` and
   verify that each companion bundle contains the remote mode and v3 policy.
   Also verify the `full` profile if it will be used. The Pi broker/admin helpers
   must run without npm, npx or runtime package installation.

4. Publish a `headless-usr` prerelease using the existing release workflow.
   Update `usr/tools/pi/runtime.pin.json` with the release's real builder revision,
   provenance digest, all three runtime asset digests/sizes, and all companion
   digests/sizes. Preserve upstream source SHAs separately from patch provenance.
   Commit that pin and install through the normal `usr` sync procedure on both
   test hosts, including companion registration.

## Actual tailnet and harness acceptance

Follow the concrete commands in [usr's guide](https://github.com/joshuarli/usr/blob/main/docs/intercom-tailnet.md).
Use disposable coordinator enrollments and record the release revision and
host/harness pair with each result.

1. Run the hub on its actual Tailscale address. Confirm it listens only on that
   address. Test reachability from the second host and denial for an unenrolled
   client. Tailscale membership alone must not authorize registration.
2. Enroll two coordinators into one fleet. Verify discovery shows the expected
   `HOST/NAME` and stable ID, then send a distinctive harmless message in both
   directions. Confirm the recipient harness receives it, not only that the
   broker accepted it. Exercise Pi/Claude, Pi/Codex and Pi/OpenCode pairs.
3. Exercise ask/reply, restart a coordinator with its saved credential, and
   confirm identity retention. Interrupt the connection or restart the hub;
   verify reconnect and queued-message behavior without creating a local broker.
4. Confirm different fleets remain isolated, duplicate active credential use
   fails, revocation disconnects the target and blocks reconnect, and remote
   clients cannot invoke local administration even with an admin-shaped frame.
5. Launch a scoped Pi SDK worker from an enrolled coordinator. Verify that the
   worker has no Intercom tools, no coordinator environment, and no peer entry.
   Repeat with the CLI leaf backends used by the bridge.
6. Preserve `inboundTrigger: "never"` and `confirmSend: true` while verifying the
   transport. Incoming receipt and automatic model wakeup are distinct behaviors;
   this change does not enable autonomous wakeups.

Record passes and failures here or in the corresponding `usr` handoff. A fixture
pass, a published asset, or successful TCP reachability is not completed two-host
acceptance.
