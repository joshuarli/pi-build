// Run against exactly the patched sources that native release builds consume,
// compiled with the locked TypeScript the headless runtime is built with.
import { spawnSync } from "node:child_process";
import { copyFileSync, cpSync, mkdirSync, mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { compilePackage } from "./headless.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
mkdirSync(join(root, ".work"), { recursive: true });
const work = mkdtempSync(join(root, ".work/intercom-tests-"));
const packages = join(work, "packages");
const compiler = join(work, "compiler");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited ${result.status ?? result.signal}`);
}

try {
  run(process.env.PYTHON || "python3", ["-I", "-X", "faulthandler", "tools/intercom.py", "prepare", packages]);
  mkdirSync(compiler);
  mkdirSync(join(work, "home"));
  for (const name of ["package.json", "package-lock.json", ".npmrc"]) copyFileSync(join(root, "locks/core-build", name), join(compiler, name));
  run("npm", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], {
    cwd: compiler,
    env: { ...process.env, HOME: join(work, "home"), npm_config_cache: join(root, ".work/npm-cache") },
  });
  const { default: ts } = await import(pathToFileURL(join(compiler, "node_modules/typescript/lib/typescript.js")).href);
  cpSync(join(packages, "agent-intercom-core/src"), join(packages, "agent-intercom-core/dist"), { recursive: true });
  for (const name of ["agent-intercom-core/dist", "agent-intercom-pi", "agent-intercom-claude", "agent-intercom-codex", "agent-intercom-opencode"]) {
    compilePackage(join(packages, name), ts);
  }
  mkdirSync(join(packages, "node_modules/@dataforxyz"), { recursive: true });
  symlinkSync(join(packages, "agent-intercom-core"), join(packages, "node_modules/@dataforxyz/agent-intercom-core"), "dir");
  if (process.env.INTERCOM_TEST_NO_SOCKETS === "1") {
    console.error("Intercom fixture mode: in-memory client transport; real socket smoke is skipped explicitly.");
  }
  run(process.execPath, ["--test", "tests/intercom-tailnet-policy.test.mjs", "tests/intercom-tailnet-transport.test.mjs"],
    { env: { ...process.env, INTERCOM_TEST_PACKAGES: packages } });
} finally {
  rmSync(work, { recursive: true, force: true });
}
