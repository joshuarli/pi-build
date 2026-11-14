import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

const packages = resolve(process.env.INTERCOM_PACKAGES_ROOT ?? process.env.INTERCOM_TEST_PACKAGES ?? ".work/intercom/packages");
function source(pkg, relative) {
  const path = join(packages, pkg, relative);
  return existsSync(path) ? path : path.replace(/\.ts$/, ".js");
}
const load = (pkg, path) => import(pathToFileURL(source(pkg, path)).href);
const { authorize, POLICY_SEMANTICS_VERSION } = await load("agent-intercom-core", "src/policy.ts");
const { POLICY_VECTORS, POLICY_VECTOR_SCHEMA_VERSION, POLICY_SEMANTICS_HASH, stateForVector } = await load("agent-intercom-core", "src/policy-vectors.ts");
const { RemoteAccessRegistry } = await load("agent-intercom-pi", "broker/access-registry.ts");
const { authorizeSessionAction, visibleSessions } = await load("agent-intercom-pi", "broker/authorization.ts");
const { createMessageReader, writeMessage } = await load("agent-intercom-pi", "broker/framing.ts");

function scratch(t) {
  // Keep Unix-domain socket paths short even on macOS.
  const dir = mkdtempSync(join(tmpdir(), "ic-policy-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function issue(registry, fleet = "personal", name = "coordinator", expiresAt) {
  const issued = registry.issueFleetEnrollment({ fleet, name, remoteHostId: `${name}-host`, ...(expiresAt ? { expiresAt } : {}) });
  return registry.consumeEnrollment(issued.enrollmentToken);
}

function session(principal) {
  return {
    id: principal.id, name: principal.name, cwd: "/fixture", model: "fixture", pid: 1, startedAt: 1, lastActivity: 1,
    origin: "remote", remoteHostId: principal.remoteHostId, remotePolicy: principal.policy,
    parentSessionId: principal.parentSessionId, rootSessionId: principal.rootSessionId,
    generation: principal.generation, canDelegate: false, depth: 1, maxDepth: 1, maxChildren: 0,
  };
}

test("semantics v3 pins its corpus and preserves every legacy vector", () => {
  assert.equal(POLICY_SEMANTICS_VERSION, 3);
  const actualHash = createHash("sha256").update(JSON.stringify({
    schemaVersion: POLICY_VECTOR_SCHEMA_VERSION, semanticsVersion: POLICY_SEMANTICS_VERSION, vectors: POLICY_VECTORS,
  })).digest("hex");
  assert.equal(actualHash, POLICY_SEMANTICS_HASH);
  for (const vector of POLICY_VECTORS) {
    const decision = authorize(stateForVector(vector), vector.actorId, vector.action, vector.targetId, vector.context);
    assert.equal(decision.allowed, vector.expectedAllowed, vector.name);
    assert.equal(decision.allowed ? decision.reason : decision.code, vector.expectedReasonOrCode, vector.name);
  }
});

test("broker authorization allows same fleet messaging and denies local, tree and administration access", (t) => {
  const registry = new RemoteAccessRegistry(join(scratch(t), "registry.json"));
  const alice = session(issue(registry, "personal", "alice").principal);
  const bob = session(issue(registry, "personal", "bob").principal);
  const stranger = session(issue(registry, "other", "stranger").principal);
  const local = { id: "local", cwd: "/private", model: "fixture", pid: 1, startedAt: 1, lastActivity: 1, origin: "local" };
  const tree = { ...session(issue(registry, "tree-fixture", "tree").principal), remotePolicy: "remote-tree", parentSessionId: "local", rootSessionId: "local" };
  const sessions = [alice, bob, stranger, local, tree];
  assert.deepEqual(visibleSessions(sessions, alice.id).map((s) => s.id).sort(), [alice.id, bob.id].sort());
  for (const action of ["discover", "send", "ask", "reply"]) {
    assert.equal(authorizeSessionAction(sessions, alice.id, action, bob.id).allowed, true, action);
    for (const target of [stranger, local, tree]) {
      assert.equal(authorizeSessionAction(sessions, alice.id, action, target.id).allowed, false, `${action} to ${target.id}`);
      assert.equal(authorizeSessionAction(sessions, target.id, action, alice.id).allowed, false, `${action} from ${target.id}`);
    }
  }
  for (const action of ["delegate_child", "inspect_tree", "adopt", "revoke"]) {
    for (const target of [alice, bob]) assert.equal(authorizeSessionAction(sessions, alice.id, action, target.id).allowed, false);
  }
});

test("fleet grants survive restart, reject replay/delegation and enforce revocation and expiry", (t) => {
  const path = join(scratch(t), "registry.json");
  let now = 1_000_000;
  const registry = new RemoteAccessRegistry(path, () => now);
  const enrollment = registry.issueFleetEnrollment({ fleet: "personal", name: "alice", remoteHostId: "mac", expiresAt: now + 5000 });
  const { principal, sessionCredential } = registry.consumeEnrollment(enrollment.enrollmentToken);
  assert.throws(() => registry.consumeEnrollment(enrollment.enrollmentToken), /invalid or already consumed/);
  assert.equal(principal.policy, "remote-fleet");
  assert.equal(principal.name, "mac/alice");
  assert.deepEqual([principal.canDelegate, principal.depth, principal.maxDepth, principal.maxChildren], [false, 1, 1, 0]);
  assert.throws(() => registry.issueChildEnrollment(principal.id, principal.generation, { name: "worker" }), /cannot delegate/);
  assert.throws(() => registry.authenticateSession(principal.id, principal.generation, "wrong"), /invalid/);
  assert.throws(() => registry.authenticateSession(principal.id, principal.generation + 1, sessionCredential), /stale/);
  const restarted = new RemoteAccessRegistry(path, () => now);
  assert.equal(restarted.authenticateSession(principal.id, 1, sessionCredential).policy, "remote-fleet");
  const summaries = restarted.inspectFleet("personal");
  assert.equal(summaries.length, 1);
  assert.equal("credentialHash" in summaries[0], false);
  assert.throws(() => restarted.adoptSubtree(principal.id, "local", "local"), /cannot be adopted/);
  now += 6000;
  assert.throws(() => restarted.authenticateSession(principal.id, 1, sessionCredential), /expired/);
  const peer = issue(restarted, "personal", "bob", now + 1000);
  restarted.revoke(peer.principal.id);
  assert.throws(() => restarted.authenticateSession(peer.principal.id, 1, peer.sessionCredential), /revoked/);
});

test("invalid fleet policies and legacy registry migrations fail closed", (t) => {
  const path = join(scratch(t), "registry.json");
  const registry = new RemoteAccessRegistry(path);
  assert.throws(() => registry.issueFleetEnrollment({ fleet: "../../bad", name: "x", remoteHostId: "x" }), /Invalid fleet/);
  assert.throws(() => registry.issueFleetEnrollment({ fleet: "personal", name: "x", remoteHostId: "a/b" }), /Invalid remote host label/);
  const qualified = registry.issueFleetEnrollment({ fleet: "personal", name: "mac/alice", remoteHostId: "mac" });
  assert.equal(registry.consumeEnrollment(qualified.enrollmentToken).principal.name, "mac/alice");
  assert.throws(() => registry.issueEnrollment({ policy: "remote-fleet", name: "x", remoteHostId: "x", parentSessionId: "local", rootSessionId: "local" }), /nondelegating/);
  const treeToken = registry.issueEnrollment({ name: "tree", remoteHostId: "host", parentSessionId: "local", rootSessionId: "local" });
  const tree = registry.consumeEnrollment(treeToken.enrollmentToken);
  const old = JSON.parse(readFileSync(path, "utf8"));
  old.version = 2;
  writeFileSync(path, JSON.stringify(old));
  assert.equal(new RemoteAccessRegistry(path).authenticateSession(tree.principal.id, 1, tree.sessionCredential).policy, "remote-tree");
  old.principals[tree.principal.id].policy = "remote-fleet";
  writeFileSync(path, JSON.stringify(old));
  assert.throws(() => new RemoteAccessRegistry(path), /nondelegating fleet grant/);
});

function peer(path) {
  const socket = net.connect(path);
  const buffered = [];
  const waiters = [];
  let failure;
  socket.on("error", (error) => { failure = error; for (const waiter of waiters.splice(0)) waiter.reject(error); });
  socket.on("data", createMessageReader((frame) => {
    const index = waiters.findIndex((waiter) => waiter.predicate(frame));
    if (index >= 0) waiters.splice(index, 1)[0].resolve(frame);
    else buffered.push(frame);
  }, (error) => socket.destroy(error)));
  return {
    socket,
    send: (frame) => writeMessage(socket, frame),
    next(predicate = () => true) {
      if (failure) return Promise.reject(failure);
      const index = buffered.findIndex(predicate);
      if (index >= 0) return Promise.resolve(buffered.splice(index, 1)[0]);
      return new Promise((resolveFrame, reject) => {
        const entry = { predicate, resolve: undefined, reject: undefined };
        const timer = setTimeout(() => {
          const index = waiters.indexOf(entry);
          if (index >= 0) waiters.splice(index, 1);
          reject(new Error("Timed out waiting for broker frame"));
        }, 4000);
        entry.resolve = (frame) => { clearTimeout(timer); resolveFrame(frame); };
        entry.reject = (error) => { clearTimeout(timer); reject(error); };
        waiters.push(entry);
      });
    },
  };
}

async function command(args, env) {
  const child = spawn(process.execPath, ["--experimental-transform-types", source("agent-intercom-pi", "broker/tailnet-admin.ts"), ...args], { env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "", stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const [code] = await once(child, "exit");
  return { code, stdout, stderr };
}

test("real broker enrolls coordinator peers through local-only administration and routes authorized messages", {
  timeout: 20_000,
  skip: process.env.INTERCOM_TEST_NO_SOCKETS === "1" ? "Executor blocks Unix socket binding; run on a host with local sockets" : false,
}, async (t) => {
  const directory = scratch(t);
  const agentDir = join(directory, "a");
  const intercom = join(agentDir, "intercom");
  mkdirSync(intercom, { recursive: true, mode: 0o700 });
  const env = { ...process.env, PI_CODING_AGENT_DIR: agentDir };
  for (const key of ["AGENT_INTERCOM_REMOTE_ENDPOINT", "AGENT_INTERCOM_REMOTE_LISTEN", "AGENT_INTERCOM_ACCESS_CREDENTIAL_PATH", "AGENT_INTERCOM_COORDINATOR"]) delete env[key];
  const broker = spawn(process.execPath, ["--experimental-transform-types", source("agent-intercom-pi", "broker/broker.ts")], { env, stdio: ["ignore", "pipe", "pipe"] });
  let output = "";
  broker.stderr.on("data", (chunk) => { output += chunk; });
  t.after(async () => {
    if (broker.exitCode === null) {
      broker.kill("SIGTERM");
      await once(broker, "exit");
    }
  });
  await new Promise((resolveStarted, reject) => {
    const timer = setTimeout(() => reject(new Error(`Broker startup timeout: ${output}`)), 4000);
    broker.stdout.on("data", (chunk) => {
      output += chunk;
      if (output.includes("Intercom broker started")) { clearTimeout(timer); resolveStarted(); }
    });
    broker.once("exit", (code) => { clearTimeout(timer); reject(new Error(`Broker exited ${code}: ${output}`)); });
  });
  const peers = [];
  t.after(() => peers.forEach((p) => p.socket.destroy()));
  async function register(name, fleet = "personal") {
    const outputPath = join(directory, `${name}.json`);
    const result = await command(["enroll", "--fleet", fleet, "--host", `${name}-host`, "--name", name, "--output", outputPath], env);
    assert.equal(result.code, 0, result.stderr);
    assert.equal(statSync(outputPath).mode & 0o777, 0o600);
    const credential = JSON.parse(readFileSync(outputPath, "utf8"));
    assert.equal(result.stdout.includes(credential.enrollmentToken), false);
    const client = peer(join(intercom, "remote-gateway.sock"));
    peers.push(client);
    client.send({ type: "register", protocol: "pi-intercom", version: 3, access: { enrollmentToken: credential.enrollmentToken },
      session: { name, cwd: "/fixture", model: "fixture", pid: process.pid, startedAt: Date.now(), lastActivity: Date.now() } });
    const response = await client.next((f) => f.type === "registered" || f.type === "error");
    assert.equal(response.type, "registered", JSON.stringify(response));
    assert.equal(response.access.canDelegate, false);
    assert.equal(response.remoteAccess.policySemanticsVersion, 3);
    return { ...client, id: response.sessionId, access: response.access, credentialPath: outputPath };
  }
  const alice = await register("alice");
  const bob = await register("bob");
  const stranger = await register("stranger", "separate");
  alice.send({ type: "list", requestId: "list" });
  const sessions = await alice.next((f) => f.type === "sessions");
  assert.deepEqual(sessions.sessions.map((s) => s.id).sort(), [alice.id, bob.id].sort());
  assert.equal(sessions.sessions.every((s) => s.remotePolicy === "remote-fleet"), true);
  const message = { id: randomUUID(), timestamp: Date.now(), content: { text: "coordinator fixture" } };
  alice.send({ type: "send", to: bob.id, message });
  const delivery = await bob.next((f) => f.type === "message");
  assert.equal(delivery.message.content.text, "coordinator fixture");
  bob.send({ type: "message_received", deliveryId: delivery.deliveryId });
  const outcome = await alice.next((f) => f.type === "delivered" || f.type === "delivery_failed");
  assert.equal(outcome.type, "delivered", JSON.stringify(outcome));
  alice.send({ type: "send", to: stranger.id, message: { ...message, id: randomUUID() } });
  assert.equal((await alice.next((f) => f.type === "delivery_failed")).accepted, false);
  const localAdmin = JSON.parse(readFileSync(join(intercom, "broker-admin.json"), "utf8"));
  const attacker = peer(join(intercom, "remote-gateway.sock"));
  peers.push(attacker);
  attacker.send({ type: "access_control", requestId: "remote-admin", adminToken: localAdmin.adminToken, action: "inspect_fleet", fleet: "personal" });
  assert.equal((await attacker.next((f) => f.type === "error")).code, "ACCESS_DENIED");
  const inspect = await command(["inspect", "--fleet", "personal"], env);
  assert.equal(inspect.code, 0, inspect.stderr);
  assert.equal(JSON.parse(inspect.stdout).length, 2);
  assert.equal(inspect.stdout.includes("credential"), false);
  const duplicate = await command(["enroll", "--fleet", "personal", "--host", "mac", "--name", "alice", "--output", alice.credentialPath], env);
  assert.notEqual(duplicate.code, 0);
  const revoke = await command(["revoke", "--session", bob.id], env);
  assert.equal(revoke.code, 0, revoke.stderr);
  assert.deepEqual(JSON.parse(revoke.stdout).changedPrincipalIds, [bob.id]);
});
