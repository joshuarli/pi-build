// Run against exactly the patched sources that native release builds consume.
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
mkdirSync(join(root, ".work"), { recursive: true });
const work = mkdtempSync(join(root, ".work/intercom-tests-"));
const packages = join(work, "packages");

function run(command, args, env = process.env) {
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", env });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited ${result.status ?? result.signal}`);
}

function compile(directory, output = directory) {
  mkdirSync(output, { recursive: true });
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.name === "node_modules") continue;
    const source = join(directory, entry.name);
    if (entry.isDirectory()) compile(source, join(output, entry.name));
    else if (entry.name.endsWith(".ts") && !entry.name.endsWith(".d.ts")) {
      const javascript = stripTypeScriptTypes(readFileSync(source, "utf8"), { mode: "transform", sourceUrl: source })
        .replace(/(from\s*["']|import\s*\(["'])([^"']+)\.ts(["'])/g, "$1$2.js$3");
      writeFileSync(join(output, entry.name.replace(/\.ts$/, ".js")), javascript);
    }
  }
}

try {
  run(process.env.PYTHON || "python3", ["-I", "tools/intercom.py", "prepare", packages]);
  // Only the shared core is a package import; all other source imports remain
  // relative. This loader setup requires no package manager or network.
  compile(join(packages, "agent-intercom-core/src"), join(packages, "agent-intercom-core/dist"));
  mkdirSync(join(packages, "node_modules/@dataforxyz"), { recursive: true });
  symlinkSync(join(packages, "agent-intercom-core"), join(packages, "node_modules/@dataforxyz/agent-intercom-core"), "dir");
  if (process.env.INTERCOM_TEST_NO_SOCKETS === "1") {
    console.error("Intercom fixture mode: in-memory client transport; real socket smoke is skipped explicitly.");
  }
  run(process.execPath, ["--experimental-transform-types", "--test",
    "tests/intercom-tailnet-policy.test.mjs", "tests/intercom-tailnet-transport.test.mjs"],
  { ...process.env, INTERCOM_PACKAGES_ROOT: packages, INTERCOM_TEST_PACKAGES: packages });
} finally {
  rmSync(work, { recursive: true, force: true });
}
