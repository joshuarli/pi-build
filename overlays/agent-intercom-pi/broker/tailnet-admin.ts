#!/usr/bin/env node
/** Local administrator for explicitly enrolled tailnet coordinator sessions. */
import { randomUUID } from "node:crypto";
import { closeSync, constants, fstatSync, fsyncSync, mkdirSync, openSync, readSync, realpathSync, unlinkSync, writeFileSync } from "node:fs";
import net from "node:net";
import { dirname, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";
import { createMessageReader, writeMessage } from "./framing.ts";
import { getBrokerAdminCredentialFilePath, getBrokerSocketPath } from "./paths.ts";

const HELP = `Usage:
  tailnet-admin enroll --fleet NAME --host HOST --name NAME --output /private/credential.json
                      [--ttl-ms 600000] [--session-ttl-ms 2592000000]
  tailnet-admin inspect --fleet NAME
  tailnet-admin revoke --session ID

Uses the local broker/admin credential under PI_CODING_AGENT_DIR (default ~/.pi/agent).
Enrollment is for coordinator sessions only. Credentials never appear in command output.
The output file is created with mode 0600 and must not already exist.
`;

function parseArgs(args: string[]): { command: string; options: Map<string, string> } {
  const [command, ...rest] = args;
  if (!command || command === "--help" || command === "-h") return { command: "help", options: new Map() };
  const supported: Record<string, string[]> = {
    enroll: ["fleet", "host", "name", "output", "ttl-ms", "session-ttl-ms"],
    inspect: ["fleet"], revoke: ["session"],
  };
  const allowed = supported[command];
  if (!allowed) throw new Error(`Unknown command: ${command}`);
  const options = new Map<string, string>();
  for (let index = 0; index < rest.length; index += 2) {
    const option = rest[index];
    const value = rest[index + 1];
    if (!option.startsWith("--") || !allowed.includes(option.slice(2)) || !value || value.startsWith("--")) {
      throw new Error(`Invalid option: ${option}`);
    }
    const name = option.slice(2);
    if (options.has(name)) throw new Error(`Repeated option: ${option}`);
    options.set(name, value);
  }
  return { command, options };
}

function required(options: Map<string, string>, name: string): string {
  const value = options.get(name);
  if (!value) throw new Error(`Missing --${name}`);
  return value;
}

function duration(options: Map<string, string>, name: string, fallback: number, maximum: number): number {
  const text = options.get(name);
  const value = text === undefined ? fallback : Number(text);
  if (!Number.isSafeInteger(value) || value <= 0 || value > maximum) throw new Error(`Invalid --${name}`);
  return value;
}

function adminToken(): string {
  const path = getBrokerAdminCredentialFilePath();
  const descriptor = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  let credential: unknown;
  try {
    const metadata = fstatSync(descriptor);
    if (!metadata.isFile() || (metadata.mode & 0o077) !== 0 || (process.getuid && metadata.uid !== process.getuid())) {
      throw new Error("The broker admin credential must be an owned private regular file");
    }
    const buffer = Buffer.alloc(16 * 1024 + 1);
    let bytes = 0;
    while (bytes < buffer.length) {
      const count = readSync(descriptor, buffer, bytes, buffer.length - bytes, null);
      if (count === 0) break;
      bytes += count;
    }
    if (bytes === buffer.length) throw new Error("The broker admin credential is too large");
    credential = JSON.parse(buffer.subarray(0, bytes).toString("utf8"));
  } finally {
    closeSync(descriptor);
  }
  if (
    !credential || typeof credential !== "object" || Array.isArray(credential)
    || !("version" in credential) || credential.version !== 1
    || !("adminToken" in credential) || typeof credential.adminToken !== "string" || credential.adminToken.length < 32
  ) throw new Error("Invalid broker admin credential");
  return credential.adminToken;
}

async function request(action: string, fields: Record<string, unknown>): Promise<Record<string, unknown>> {
  const token = adminToken();
  return await new Promise((resolveRequest, reject) => {
    // Never use getBrokerConnectTarget here: administration stays on the local
    // authority socket even when the invoking shell has remote client variables.
    const socket = net.connect(getBrokerSocketPath());
    const requestId = randomUUID();
    let settled = false;
    const finish = (error?: Error, response?: Record<string, unknown>) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      socket.destroy();
      if (error) reject(error);
      else resolveRequest(response!);
    };
    const timeout = setTimeout(() => finish(new Error("Local broker request timed out")), 5000);
    socket.on("error", (error) => finish(new Error(`Cannot contact local Intercom broker: ${error.message}`)));
    socket.on("close", () => finish(new Error("Local broker closed before replying")));
    socket.on("data", createMessageReader((value) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) return finish(new Error("Invalid broker response"));
      const response = value as Record<string, unknown>;
      if (response.type === "error") return finish(new Error(`Broker rejected ${action}: ${String(response.code ?? "ERROR")}`));
      if (response.type !== "access_control_result" || response.requestId !== requestId || response.action !== action) {
        return finish(new Error("Unexpected broker response"));
      }
      finish(undefined, response);
    }, (error) => finish(error)));
    socket.on("connect", () => writeMessage(socket, { type: "access_control", requestId, adminToken: token, action, ...fields }));
  });
}

export async function main(args: string[] = process.argv.slice(2)): Promise<void> {
  const { command, options } = parseArgs(args);
  if (command === "help") {
    process.stdout.write(HELP);
    return;
  }
  if (command === "inspect") {
    const result = await request("inspect_fleet", { fleet: required(options, "fleet") });
    process.stdout.write(`${JSON.stringify(result.principals, null, 2)}\n`);
    return;
  }
  if (command === "revoke") {
    const result = await request("revoke_subtree", { principalId: required(options, "session") });
    process.stdout.write(`${JSON.stringify({ changedPrincipalIds: result.changedPrincipalIds })}\n`);
    return;
  }
  const fleet = required(options, "fleet");
  const host = required(options, "host");
  const name = required(options, "name");
  const output = required(options, "output");
  if (!isAbsolute(output)) throw new Error("--output must be an absolute path");
  const ttlMs = duration(options, "ttl-ms", 600_000, 86_400_000);
  const sessionTtlMs = duration(options, "session-ttl-ms", 2_592_000_000, 2_592_000_000);
  mkdirSync(dirname(output), { recursive: true, mode: 0o700 });
  // Exclusive creation prevents replacing another live session's credential,
  // including a symlink or a previously used enrollment file.
  const descriptor = openSync(output, "wx", 0o600);
  let written = false;
  try {
    const result = await request("issue_fleet_enrollment", {
      enrollment: { fleet, name, remoteHostId: host, ttlMs, expiresAt: Date.now() + sessionTtlMs },
    });
    if (typeof result.enrollmentToken !== "string" || typeof result.expiresAt !== "number") {
      throw new Error("Invalid enrollment response");
    }
    writeFileSync(descriptor, `${JSON.stringify({ version: 1, enrollmentToken: result.enrollmentToken })}\n`);
    fsyncSync(descriptor);
    written = true;
    process.stdout.write(`${JSON.stringify({ credentialPath: output, fleet, enrollmentExpiresAt: result.expiresAt })}\n`);
  } finally {
    closeSync(descriptor);
    if (!written) unlinkSync(output);
  }
}

// Node resolves symlinks for import.meta.url but not argv[1]; installed
// runtimes are reached through the pi-runtime/current symlink.
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    process.stderr.write(`tailnet-admin: ${error instanceof Error ? error.message : "request failed"}\n`);
    process.exitCode = 1;
  });
}
