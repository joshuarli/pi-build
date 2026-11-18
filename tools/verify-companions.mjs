import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const directory = process.argv[2];
if (!directory) throw new Error("usage: node tools/verify-companions.mjs DIST_PROFILE_DIRECTORY");
const kinds = ["claude", "codex", "opencode"];
const archives = new Map();
for (const archive of readdirSync(directory).sort()) {
  const match = /^agent-intercom-([a-z]+)-(\d+\.\d+\.\d+)\.tgz$/.exec(archive);
  if (match === null) continue;
  const [, kind, version] = match;
  if (!kinds.includes(kind)) continue;
  const existing = archives.get(kind);
  if (existing)
    throw new Error(`expected exactly one ${kind} companion archive in ${directory}, found: ${existing.archive}, ${archive}`);
  archives.set(kind, { archive, version });
}
for (const kind of kinds) {
  if (!archives.has(kind))
    throw new Error(`expected exactly one ${kind} companion archive in ${directory}, found none`);
}

const work = mkdtempSync(join(tmpdir(), "verify-companions-"));
try {
  for (const [kind, { archive, version }] of archives) {
    const extract = join(work, archive.replace(/\.tgz$/, ""));
    mkdirSync(extract);
    const unpack = spawnSync("tar", ["-xzf", join(directory, archive), "-C", extract]);
    if (unpack.status !== 0) throw new Error(`${archive}: tar exited ${unpack.status}`);
    const pkgDir = join(extract, "package");
    const manifest = join(pkgDir, "package.json");
    if (!existsSync(manifest)) throw new Error(`${archive}: missing package/package.json`);
    const pkg = JSON.parse(readFileSync(manifest, "utf8"));
    const expectedName = `@dataforxyz/agent-intercom-${kind}`;
    if (pkg.name !== expectedName)
      throw new Error(`${archive}: package.json name ${pkg.name} != archive package ${expectedName}`);
    if (pkg.version !== version)
      throw new Error(`${archive}: package.json version ${pkg.version} != archive version ${version}`);
    const bins = pkg.bin == null ? [] : typeof pkg.bin === "string" ? [pkg.bin] : Object.values(pkg.bin);
    const verifyFile = (file, label) => {
      if (!existsSync(file)) throw new Error(`${archive}: missing ${label} ${file}`);
      if (!statSync(file).isFile()) throw new Error(`${archive}: ${label} ${file} is not a regular file`);
      const result = spawnSync(process.execPath, ["--check", file], { stdio: "pipe" });
      if (result.status !== 0)
        throw new Error(`${archive}: ${file} failed syntax check: ${result.stderr}`);
    };
    if (bins.length > 0) {
      for (const bin of bins) verifyFile(join(pkgDir, bin), "bin entry");
    } else {
      const exportTargets = [];
      const collect = (value) => {
        if (typeof value === "string") exportTargets.push(value);
        else if (value && typeof value === "object")
          for (const nested of Object.values(value)) collect(nested);
      };
      collect(pkg.exports ?? (pkg.main ? { main: pkg.main } : null));
      if (exportTargets.length === 0)
        throw new Error(`${archive}: no executable entry points (no bin, exports, or main)`);
      for (const entry of new Set(exportTargets)) verifyFile(join(pkgDir, entry), "export");
    }
    if (kind === "opencode") {
      const plugin = join(pkgDir, "node_modules/@opencode-ai/plugin/dist/index.js");
      if (!existsSync(plugin)) throw new Error(`${archive}: @opencode-ai/plugin is not vendored`);
      const core = join(pkgDir, "node_modules/@dataforxyz/agent-intercom-core/dist/index.js");
      if (!existsSync(core)) throw new Error(`${archive}: @dataforxyz/agent-intercom-core is not vendored`);
    }
    console.log(`ok: ${pkg.name} ${version}`);
  }
} finally {
  rmSync(work, { recursive: true, force: true });
}
