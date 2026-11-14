import assert from "node:assert/strict";
import { after, test } from "node:test";
import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import { chmodSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import { duplexPair } from "node:stream";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Exercise the actual patched clients without model calls or a tailnet. Run
// through `make test-intercom`, which supplies the compiled patched packages.
if (!process.env.INTERCOM_TEST_PACKAGES) throw new Error("INTERCOM_TEST_PACKAGES is required; run make test-intercom");
const prepared = resolve(process.env.INTERCOM_TEST_PACKAGES);
const temporary = mkdtempSync(join(tmpdir(), "ict-"));
const packages = join(temporary, "packages");
const names = ["pi", "claude", "codex", "opencode"];
const environmentKeys = ["PI_CODING_AGENT_DIR", "AGENT_INTERCOM_REMOTE_ENDPOINT", "AGENT_INTERCOM_ACCESS_CREDENTIAL_PATH", "AGENT_INTERCOM_REMOTE_LISTEN"];
const oldEnvironment = Object.fromEntries(environmentKeys.map((key) => [key, process.env[key]]));
const memoryTransport = process.env.INTERCOM_TEST_NO_SOCKETS === "1";
const memoryEndpoints = new Map();
const originalConnect = net.connect;
if (memoryTransport) {
  net.connect = (target) => {
    const [client, server] = duplexPair();
    queueMicrotask(() => {
      const accept = memoryEndpoints.get(target);
      if (accept) {
        accept(server);
        client.emit("connect");
      } else {
        server.destroy();
        client.destroy(Object.assign(new Error(`connect ENOENT ${target}`), { code: "ENOENT" }));
      }
    });
    return client;
  };
}
for (const key of environmentKeys) delete process.env[key];
process.env.PI_CODING_AGENT_DIR = join(temporary, "agent");

after(() => {
  net.connect = originalConnect;
  for (const key of environmentKeys) {
    if (oldEnvironment[key] === undefined) delete process.env[key];
    else process.env[key] = oldEnvironment[key];
  }
  rmSync(temporary, { recursive: true, force: true });
});

for (const name of [...names, "core"]) {
  cpSync(join(prepared, `agent-intercom-${name}`), join(packages, `agent-intercom-${name}`), { recursive: true });
}
mkdirSync(join(packages, "node_modules", "@dataforxyz"), { recursive: true });
symlinkSync(join(packages, "agent-intercom-core"), join(packages, "node_modules", "@dataforxyz", "agent-intercom-core"), "dir");

const { POLICY_SEMANTICS_VERSION } = await import(pathToFileURL(join(packages, "agent-intercom-core/dist/policy.js")));
const { POLICY_SEMANTICS_HASH } = await import(pathToFileURL(join(packages, "agent-intercom-core/dist/policy-vectors.js")));
const adapters = [];
for (const name of names) {
  const broker = join(packages, `agent-intercom-${name}`, "broker");
  adapters.push({
    name,
    paths: await import(pathToFileURL(join(broker, "paths.js"))),
    transport: await import(pathToFileURL(join(broker, "remote-transport.js"))),
    spawn: await import(pathToFileURL(join(broker, "spawn.js"))),
    Client: (await import(pathToFileURL(join(broker, "client.js")))).IntercomClient,
  });
}

test("Pi excludes scoped and native child workers before registering Intercom", async () => {
  const { isCoordinatorSession } = await import(pathToFileURL(join(packages, "agent-intercom-pi/coordinator-scope.js")));
  assert.equal(isCoordinatorSession({}), true);
  assert.equal(isCoordinatorSession({ PI_SUBAGENT_CHILD: "0", USR_SCOPED_WORKER: "0" }), true);
  assert.equal(isCoordinatorSession({ PI_SUBAGENT_CHILD: "1" }), false);
  assert.equal(isCoordinatorSession({ USR_SCOPED_WORKER: "1" }), false);
  assert.equal(isCoordinatorSession({ USR_REQUIRED_CHILD_EXTENSIONS_JSON: "[]" }), false);
  assert.equal(isCoordinatorSession({ USR_REQUIRED_CHILD_EXTENSIONS_JSON: "" }), false);
});

function credential(name, value = { enrollmentToken: "test-enrollment" }) {
  const path = join(temporary, `${name}-${randomUUID()}.json`);
  writeFileSync(path, JSON.stringify(value), { mode: 0o600 });
  return path;
}

function remoteEnvironment(endpoint, path) {
  return { AGENT_INTERCOM_REMOTE_ENDPOINT: endpoint, AGENT_INTERCOM_ACCESS_CREDENTIAL_PATH: path };
}

function configure(endpoint, path) {
  for (const key of ["AGENT_INTERCOM_REMOTE_ENDPOINT", "AGENT_INTERCOM_ACCESS_CREDENTIAL_PATH", "AGENT_INTERCOM_REMOTE_LISTEN"]) delete process.env[key];
  if (endpoint !== undefined) process.env.AGENT_INTERCOM_REMOTE_ENDPOINT = endpoint;
  if (path !== undefined) process.env.AGENT_INTERCOM_ACCESS_CREDENTIAL_PATH = path;
}

function writeFrame(socket, frame) {
  const body = Buffer.from(JSON.stringify(frame));
  const header = Buffer.alloc(4);
  header.writeUInt32BE(body.length);
  socket.write(Buffer.concat([header, body]));
}

async function gateway(onFrame) {
  const path = join(temporary, `${randomUUID()}.sock`);
  const sockets = new Set();
  const received = [];
  const accept = (socket) => {
    sockets.add(socket);
    socket.on("error", () => {});
    socket.on("close", () => sockets.delete(socket));
    let pending = Buffer.alloc(0);
    socket.on("data", (data) => {
      pending = Buffer.concat([pending, data]);
      while (pending.length >= 4 && pending.length >= 4 + pending.readUInt32BE(0)) {
        const size = pending.readUInt32BE(0);
        assert.ok(size < 1024 * 1024);
        const frame = JSON.parse(pending.subarray(4, 4 + size).toString());
        pending = pending.subarray(4 + size);
        received.push(frame);
        if (frame.type === "unregister") socket.end();
        else onFrame(socket, frame);
      }
    });
  };
  const server = memoryTransport ? undefined : net.createServer(accept);
  if (server) await new Promise((resolve, reject) => { server.once("error", reject); server.listen(path, resolve); });
  else memoryEndpoints.set(path, accept);
  return {
    endpoint: `unix://${path}`,
    received,
    async close() {
      for (const socket of sockets) socket.destroy();
      if (server) await new Promise((resolve) => server.close(resolve));
      else memoryEndpoints.delete(path);
    },
  };
}

function registered(sessionId, override = {}) {
  return {
    type: "registered", protocol: "pi-intercom", version: 3, sessionId,
    remoteAccess: { feature: "remote-access-v1", policySemanticsVersion: POLICY_SEMANTICS_VERSION, policySemanticsHash: POLICY_SEMANTICS_HASH },
    access: {
      origin: "remote", remoteHostId: "test-host", parentSessionId: "root", rootSessionId: "root",
      generation: 1, canDelegate: false, depth: 1, maxDepth: 1, maxChildren: 0,
      sessionCredential: "test-session-credential",
    },
    ...override,
  };
}

function registration() {
  return { name: "test-host/coordinator", cwd: temporary, model: "test", pid: process.pid, startedAt: Date.now(), lastActivity: Date.now() };
}

for (const adapter of adapters) {
  test(`${adapter.name}: local defaults and explicit remote endpoint validation`, () => {
    const { getBrokerConnectTarget, getRemoteBrokerListenTarget } = adapter.paths;
    assert.equal(getBrokerConnectTarget("linux", { PI_CODING_AGENT_DIR: join(temporary, "agent") }), join(temporary, "agent", "intercom", "broker.sock"));
    const path = credential(adapter.name);
    for (const address of ["100.64.0.1", "100.127.255.254", "[fd7a:115c:a1e0::1]"]) {
      const target = getBrokerConnectTarget("linux", remoteEnvironment(`tcp://${address}:4321`, path));
      assert.equal(target.port, 4321);
      assert.equal(target.transport, "tcp");
    }
    const socketPath = join(temporary, "gateway.sock");
    assert.equal(getBrokerConnectTarget("darwin", remoteEnvironment(`unix://${socketPath}`, path)), socketPath);
    for (const endpoint of ["", "tcp://0.0.0.0:4321", "tcp://127.0.0.1:4321", "tcp://100.63.0.1:4321", "tcp://100.128.0.1:4321", "tcp://example.ts.net:4321", "tcp://[::]:4321", "tcp://[fd7a:115c:a1e1::1]:4321", "tcp://100.64.0.1:0", "tcp://100.64.0.1:65536", "tcp://100.64.0.1:4321/path", "tcp://user:pass@100.64.0.1:4321", "tcp://100.64.0.1:4321?x=y", "unix://host/tmp/socket", "unix:///tmp/socket%00", "unix:///tmp/socket#fragment"]) {
      assert.throws(() => getBrokerConnectTarget("linux", remoteEnvironment(endpoint, path)), undefined, endpoint);
      assert.throws(() => getRemoteBrokerListenTarget({ AGENT_INTERCOM_REMOTE_LISTEN: endpoint }), undefined, endpoint);
    }
    assert.throws(() => getBrokerConnectTarget("linux", { AGENT_INTERCOM_REMOTE_ENDPOINT: `unix://${socketPath}` }), /requires an absolute/);
    assert.throws(() => getBrokerConnectTarget("linux", remoteEnvironment(`unix://${socketPath}`, "relative.json")), /requires an absolute/);
    assert.throws(() => getBrokerConnectTarget("linux", { AGENT_INTERCOM_ACCESS_CREDENTIAL_PATH: path }), /refusing local fallback/);
    assert.throws(() => getRemoteBrokerListenTarget({ ...remoteEnvironment(`unix://${socketPath}`, path), AGENT_INTERCOM_REMOTE_LISTEN: "tcp://100.64.0.1:4321" }), /cannot be enabled/);
  });

  test(`${adapter.name}: remote mode never spawns or falls back to a local broker`, async () => {
    const path = credential(adapter.name);
    configure(`unix://${join(temporary, "missing.sock")}`, path);
    await adapter.spawn.spawnBrokerIfNeeded("/must-not-run", []);
    const client = new adapter.Client();
    client.on("error", () => {});
    await assert.rejects(client.connect(registration()), /ENOENT/);
    assert.equal(client.sessionId, null);
    assert.equal(existsSync(join(temporary, "agent/intercom/broker.pid")), false);
    configure(undefined, path);
    await assert.rejects(adapter.spawn.spawnBrokerIfNeeded("/must-not-run", []), /refusing local fallback/);
    configure(undefined, undefined);
  });

  test(`${adapter.name}: remote credentials must be private regular files`, () => {
    const path = credential(adapter.name);
    assert.equal(JSON.parse(adapter.transport.readRemoteCredential(path)).enrollmentToken, "test-enrollment");
    chmodSync(path, 0o644);
    assert.throws(() => adapter.transport.readRemoteCredential(path), /mode 0600/);
    const link = `${path}.link`;
    symlinkSync(path, link);
    assert.throws(() => adapter.transport.readRemoteCredential(link));
  });

  test(`${adapter.name}: actual client enrolls, sends, and retains remote identity on reconnect`, async () => {
    const id = randomUUID();
    const path = credential(adapter.name);
    const peer = { ...registration(), id: "peer", trustedLocal: false, origin: "remote", remoteHostId: "other-host" };
    const server = await gateway((socket, frame) => {
      if (frame.type === "register") writeFrame(socket, registered(id));
      else if (frame.type === "list") writeFrame(socket, { type: "sessions", requestId: frame.requestId, sessions: [peer] });
      else if (frame.type === "send") {
        writeFrame(socket, { type: "delivery_accepted", messageId: frame.message.id, deliveryId: "delivery-test" });
        writeFrame(socket, { type: "delivered", messageId: frame.message.id, deliveryId: "delivery-test" });
      }
    });
    configure(server.endpoint, path);
    const client = new adapter.Client();
    client.on("error", () => {});
    try {
      await adapter.spawn.spawnBrokerIfNeeded("/must-not-run", []);
      await client.connect(registration(), "ignored-local-transcript-id");
      assert.equal(client.sessionId, id);
      assert.deepEqual(server.received[0].access, { enrollmentToken: "test-enrollment" });
      assert.equal(server.received[0].sessionId, undefined);
      assert.equal(JSON.parse(readFileSync(path, "utf8")).sessionId, id);
      assert.equal((await client.listSessions())[0].remoteHostId, "other-host");
      const result = await client.send("peer", { text: "tailnet transport test" });
      assert.equal(result.delivered, true);
      await client.disconnect(true);
      await client.connect(registration(), "another-local-id");
      assert.equal(client.sessionId, id);
      const reconnect = server.received.filter((frame) => frame.type === "register")[1];
      assert.equal(reconnect.access.sessionId, id);
      assert.equal(reconnect.access.sessionCredential, "test-session-credential");
      assert.equal(reconnect.access.generation, 1);
      assert.equal(reconnect.sessionId, undefined);
    } finally {
      await client.disconnect(true);
      await server.close();
      configure(undefined, undefined);
    }
  });

  test(`${adapter.name}: rejects a remote broker with missing or incompatible policy negotiation`, async () => {
    for (const remoteAccess of [undefined, { feature: "remote-access-v1", policySemanticsVersion: POLICY_SEMANTICS_VERSION, policySemanticsHash: "wrong-hash" }]) {
      const server = await gateway((socket, frame) => { if (frame.type === "register") writeFrame(socket, registered(randomUUID(), { remoteAccess })); });
      const path = credential(adapter.name);
      configure(server.endpoint, path);
      const client = new adapter.Client();
      client.on("error", () => {});
      try {
        await assert.rejects(client.connect(registration()), /registered message|policy contract/);
        assert.equal(client.sessionId, null);
        assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), { enrollmentToken: "test-enrollment" });
      } finally {
        await client.disconnect(true);
        await server.close();
        configure(undefined, undefined);
      }
    }
  });

  test(`${adapter.name}: reconnect rejects a changed broker identity or generation`, async () => {
    const id = randomUUID();
    const path = credential(adapter.name, { version: 1, sessionCredential: "test-session-credential", sessionId: id, generation: 1 });
    const server = await gateway((socket, frame) => { if (frame.type === "register") writeFrame(socket, registered(randomUUID())); });
    configure(server.endpoint, path);
    const client = new adapter.Client();
    client.on("error", () => {});
    try {
      await assert.rejects(client.connect(registration()), /identity or generation/);
      assert.equal(client.sessionId, null);
      assert.equal(JSON.parse(readFileSync(path, "utf8")).sessionId, id);
    } finally {
      await client.disconnect(true);
      await server.close();
      configure(undefined, undefined);
    }
  });
}

test("canonical broker enrolls and routes all four coordinators with fleet isolation", { timeout: 20000 }, async () => {
  assert.equal(POLICY_SEMANTICS_VERSION, 3, "Apply the tailnet policy patch before broker integration");
  const originalCreateServer = net.createServer;
  const originalSignals = new Map(["SIGTERM", "SIGINT"].map((signal) => [signal, new Set(process.listeners(signal))]));
  if (memoryTransport) {
    class MemoryServer extends EventEmitter {
      listening = false;
      constructor(accept) { super(); this.accept = accept; }
      listen(target, callback) {
        assert.equal(typeof target, "string", "socketless fixture only accepts explicit Unix targets");
        this.target = target;
        writeFileSync(target, "", { mode: 0o600 });
        memoryEndpoints.set(target, this.accept);
        this.listening = true;
        queueMicrotask(() => { this.emit("listening"); callback?.(); });
        return this;
      }
      close(callback) {
        memoryEndpoints.delete(this.target);
        this.listening = false;
        callback?.();
        return this;
      }
    }
    net.createServer = (accept) => new MemoryServer(accept);
  }

  // A test-only export lets the real broker run under the explicit transport
  // fixture. Production source and its process-level shutdown remain intact.
  const brokerPath = join(packages, "agent-intercom-pi/broker/broker.js");
  const brokerSource = readFileSync(brokerPath, "utf8");
  assert.ok(brokerSource.includes("new IntercomBroker().start();"));
  writeFileSync(`${brokerPath}.test.js`, brokerSource
    .replace("new IntercomBroker().start();", "export { IntercomBroker };")
    .replace("process.exit(0);", "return;"));
  const endpointPath = join(temporary, "hub.sock");
  const localPath = join(temporary, "agent/intercom/broker.sock");
  configure(undefined, undefined);
  process.env.AGENT_INTERCOM_REMOTE_LISTEN = `unix://${endpointPath}`;
  let broker;
  const liveClients = [];
  const credentials = [];
  const delivered = [];

  function exchange(path, request) {
    return new Promise((resolve, reject) => {
      const socket = net.connect(path);
      const timeout = setTimeout(() => { socket.destroy(); reject(new Error("Broker exchange timed out")); }, 3000);
      let pending = Buffer.alloc(0);
      socket.on("error", (error) => { clearTimeout(timeout); reject(error); });
      socket.on("data", (data) => {
        pending = Buffer.concat([pending, data]);
        if (pending.length < 4 || pending.length < 4 + pending.readUInt32BE(0)) return;
        clearTimeout(timeout);
        const response = JSON.parse(pending.subarray(4, 4 + pending.readUInt32BE(0)).toString());
        socket.end();
        resolve(response);
      });
      writeFrame(socket, request);
    });
  }

  try {
    const { IntercomBroker } = await import(pathToFileURL(`${brokerPath}.test.js`));
    broker = new IntercomBroker();
    broker.start();
    const pidPath = join(temporary, "agent/intercom/broker.pid");
    for (let attempts = 0; !existsSync(pidPath) && attempts < 100; attempts++) await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(existsSync(pidPath), true, "all broker listeners became ready");
    const { adminToken } = JSON.parse(readFileSync(join(temporary, "agent/intercom/broker-admin.json"), "utf8"));
    const deniedAdmin = await exchange(endpointPath, { type: "access_control", requestId: randomUUID(), adminToken, action: "inspect_fleet", fleet: "test" });
    assert.equal(deniedAdmin.type, "error");
    assert.equal(deniedAdmin.code, "ACCESS_DENIED");
    const deniedRegistration = await exchange(endpointPath, { type: "register", protocol: "pi-intercom", version: 3, session: registration() });
    assert.equal(deniedRegistration.code, "ACCESS_DENIED");

    for (const [index, adapter] of adapters.entries()) {
      const issued = await exchange(localPath, {
        type: "access_control", requestId: randomUUID(), adminToken, action: "issue_fleet_enrollment",
        enrollment: { fleet: "test", name: adapter.name, remoteHostId: `host-${index}`, ttlMs: 60000 },
      });
      assert.equal(issued.type, "access_control_result");
      const path = credential(`hub-${adapter.name}`, { enrollmentToken: issued.enrollmentToken });
      credentials.push(path);
      configure(`unix://${endpointPath}`, path);
      const client = new adapter.Client();
      client.on("error", () => {});
      client.on("message", (from, message, deliveryId) => {
        delivered.push({ index, from, message });
        client.acknowledgeMessage(deliveryId);
      });
      await client.connect(registration());
      liveClients.push(client);
    }
    for (const [index, client] of liveClients.entries()) {
      const sessions = await client.listSessions();
      assert.equal(sessions.length, 4);
      assert.ok(sessions.every((session) => session.origin === "remote" && session.trustedLocal === false));
      assert.ok(sessions.some((session) => session.name === `host-${index}/${adapters[index].name}`));
      const result = await client.send(liveClients[(index + 1) % 4].sessionId, { text: `coordinator-${index}` });
      assert.equal(result.accepted, true);
      assert.equal(result.delivered, true);
    }
    assert.equal(delivered.length, 4);
    const stableId = liveClients[0].sessionId;
    await liveClients[0].disconnect(true);
    configure(`unix://${endpointPath}`, credentials[0]);
    await liveClients[0].connect(registration());
    assert.equal(liveClients[0].sessionId, stableId);
    const issuedOther = await exchange(localPath, {
      type: "access_control", requestId: randomUUID(), adminToken, action: "issue_fleet_enrollment",
      enrollment: { fleet: "other", name: "isolated", remoteHostId: "other-host", ttlMs: 60000 },
    });
    const otherCredential = credential("other-fleet", { enrollmentToken: issuedOther.enrollmentToken });
    configure(`unix://${endpointPath}`, otherCredential);
    const isolated = new adapters[0].Client();
    isolated.on("error", () => {});
    await isolated.connect(registration());
    liveClients.push(isolated);
    assert.deepEqual((await isolated.listSessions()).map((session) => session.id), [isolated.sessionId]);
    assert.equal((await isolated.send(stableId, { text: "must not cross fleet" })).delivered, false);
    assert.equal(delivered.length, 4);

    for (const client of liveClients) await client.disconnect(true);
    // Explicit hub mode must outlive the ordinary broker's five-second idle exit.
    await new Promise((resolve) => setTimeout(resolve, 5150));
    const health = await exchange(endpointPath, { type: "health", requestId: randomUUID() });
    assert.equal(health.endpoint, "remote");
  } finally {
    for (const client of liveClients) await client.disconnect(true);
    broker?.shutdown();
    for (const [signal, prior] of originalSignals) {
      for (const listener of process.listeners(signal)) if (!prior.has(listener)) process.off(signal, listener);
    }
    net.createServer = originalCreateServer;
    configure(undefined, undefined);
  }
});
