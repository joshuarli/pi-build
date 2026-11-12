import { chmodSync, existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync, symlinkSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const runtime = process.argv[2];
if (!runtime) throw new Error("usage: node tools/verify.mjs EXTRACTED_ROOT");
const modules = join(runtime, "node_modules");
const work = join(process.cwd(), ".work/verify");
const cwd = join(work, "cwd");
const binDir = join(work, "bin");
const museCalls = join(work, "muse-calls");
const agentDir = join(work, "agent");
const home = join(work, "home");
mkdirSync(cwd, { recursive: true });
mkdirSync(agentDir, { recursive: true });
mkdirSync(home, { recursive: true });
mkdirSync(binDir, { recursive: true });
mkdirSync(join(agentDir, "intercom"), { recursive: true });
writeFileSync(join(agentDir, "intercom", "config.json"), JSON.stringify({ enabled: false }));
const fakeMuse = join(binDir, "muse");
writeFileSync(fakeMuse, `#!/bin/sh\nprintf called >> ${museCalls}\n`);
chmodSync(fakeMuse, 0o755);
for (const name of ["npm", "npx"]) {
  const path = join(binDir, name);
  if (existsSync(path)) unlinkSync(path);
  symlinkSync(fakeMuse, path);
}
if (existsSync(museCalls)) unlinkSync(museCalls);
process.env.HOME = home;
process.env.XDG_CONFIG_HOME = join(home, ".config");
process.env.XDG_DATA_HOME = join(home, ".local/share");
process.env.XDG_CACHE_HOME = join(home, ".cache");
process.env.PI_CODING_AGENT_DIR = agentDir;
process.env.PATH = binDir + ":" + process.env.PATH;
process.env.PI_OFFLINE = "1";
process.env.PI_SKIP_VERSION_CHECK = "1";
const sdk = await import(pathToFileURL(join(modules, "@earendil-works/pi-coding-agent/dist/index.js")));
const { emitSessionShutdownEvent } = await import(pathToFileURL(join(modules, "@earendil-works/pi-coding-agent/dist/core/extensions/runner.js")));
const runtimeModels = await sdk.ModelRuntime.create();
const settingsManager = sdk.SettingsManager.inMemory({});
const sessionManager = sdk.SessionManager.create(cwd, join(work, "session"));
const resourceLoader = new sdk.DefaultResourceLoader({
  cwd,
  agentDir,
  settingsManager,
  noSkills: true,
  noPromptTemplates: true,
  noThemes: true,
  noContextFiles: true,
  additionalExtensionPaths: [
    join(modules, "pi-subagents/index.ts"),
    join(modules, "@dataforxyz/agent-intercom-pi/index.ts"),
    join(modules, "pi-muse-subscription/src/index.ts"),
  ],
});
await resourceLoader.reload();
const errors = resourceLoader.getExtensions().errors;
if (errors.length) throw new Error(errors.map((error) => String(error.error)).join("; "));
const { session } = await sdk.createAgentSession({
  cwd,
  agentDir,
  modelRuntime: runtimeModels,
  sessionManager,
  settingsManager,
  resourceLoader,
  noTools: "builtin",
});
try {
  await session.bindExtensions({});
  const ember = runtimeModels.getModel("muse-sdk", "muse-ember-1.0");
  const spark = runtimeModels.getModel("muse-sdk", "muse-spark-1.3");
  if (!ember || !spark) throw new Error("bundled Muse Ember and Spark models were not registered");
  if (ember.maxTokens !== 524_288 || ember.thinkingLevelMap.xhigh !== "xhigh")
    throw new Error("bundled Muse Ember limits or xhigh effort changed");
  await new Promise((resolve) => setTimeout(resolve, 250));
  if (existsSync(museCalls) && readFileSync(museCalls, "utf8").length)
    throw new Error("offline Muse session launched the Muse executable");
  console.log(`ok: loaded and bound ${session.extensionRunner.extensions.length} Pi extensions; Muse Ember and Spark registered offline`);
} finally {
  await emitSessionShutdownEvent(session.extensionRunner, { type: "session_shutdown", reason: "quit" });
  session.dispose();
}
