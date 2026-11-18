import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const verifier = fileURLToPath(new URL("../tools/verify-companions.mjs", import.meta.url));
const scope = "@dataforxyz/agent-intercom-";

function verify(t, entries) {
  const root = mkdtempSync(join(tmpdir(), "companion-fixture-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const dist = join(root, "dist");
  const pkg = join(root, "package");
  mkdirSync(dist);
  mkdirSync(pkg);
  writeFileSync(join(pkg, "index.js"), "module.exports = 1;\n");
  for (const [kind, version, pkgKind = kind] of entries) {
    if (pkgKind === "opencode") {
      for (const name of ["@opencode-ai/plugin", "@dataforxyz/agent-intercom-core"]) {
        const library = join(pkg, "node_modules", name, "dist");
        mkdirSync(library, { recursive: true });
        writeFileSync(join(library, "index.js"), "module.exports = 1;\n");
      }
    }
    writeFileSync(join(pkg, "package.json"), JSON.stringify({
      name: scope + pkgKind,
      version,
      main: "index.js",
    }));
    const archive = join(dist, `agent-intercom-${kind}-${version}.tgz`);
    const tar = spawnSync("tar", ["-czf", archive, "-C", root, "package"], { encoding: "utf8" });
    assert.equal(tar.status, 0, tar.stderr);
  }
  return spawnSync(process.execPath, [verifier, dist], { encoding: "utf8" });
}

test("verifies one archive for each companion", (t) => {
  const result = verify(t, [["claude", "1.0.0"], ["codex", "1.0.1"], ["opencode", "1.0.2"]]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, [
    `ok: ${scope}claude 1.0.0`,
    `ok: ${scope}codex 1.0.1`,
    `ok: ${scope}opencode 1.0.2`,
    "",
  ].join("\n"));
});

test("rejects three versions of a single companion", (t) => {
  const result = verify(t, [["claude", "1.0.0"], ["claude", "1.0.1"], ["claude", "1.0.2"]]);
  assert.equal(result.status, 1, result.stdout);
  assert.match(result.stderr, /expected exactly one claude companion archive/);
  assert.equal(result.stdout, "");
});

test("rejects a missing companion before checking the others", (t) => {
  const result = verify(t, [["claude", "1.0.0"], ["codex", "1.0.1"]]);
  assert.equal(result.status, 1, result.stdout);
  assert.match(result.stderr, /expected exactly one opencode companion archive.*found none/);
  assert.equal(result.stdout, "");
});

test("rejects an archive containing a different package name", (t) => {
  const result = verify(t, [["claude", "1.0.0", "codex"], ["codex", "1.0.1"], ["opencode", "1.0.2"]]);
  assert.equal(result.status, 1, result.stdout);
  assert.match(result.stderr, /package\.json name @dataforxyz\/agent-intercom-codex != archive package @dataforxyz\/agent-intercom-claude/);
  assert.equal(result.stdout, "");
});
