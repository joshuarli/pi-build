import { readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const extensionPackages = ["pi-subagents", "@dataforxyz/agent-intercom-pi", "pi-muse-subscription"];
const removedPackages = ["tsx", "esbuild", "@esbuild", "@aws-sdk", "@smithy", "@aws/lambda-invoke-store"];
const bedrockModules = [
  "@earendil-works/pi-ai/dist/api/bedrock-converse-stream.js",
  "@earendil-works/pi-coding-agent/dist/bundle/chunks/bedrock-converse-stream.js",
];

function compilePackage(root, ts) {
  for (const entry of readdirSync(root, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "node_modules") compilePackage(path, ts);
    } else if (entry.isFile() && entry.name.endsWith(".ts") && !entry.name.endsWith(".d.ts")) {
      const result = ts.transpileModule(readFileSync(path, "utf8"), {
        fileName: path,
        reportDiagnostics: true,
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          module: ts.ModuleKind.ESNext,
          rewriteRelativeImportExtensions: true,
          removeComments: true,
        },
      });
      const errors = result.diagnostics.filter((diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error);
      if (errors.length) throw new Error(ts.formatDiagnostics(errors, {
        getCanonicalFileName: (file) => file,
        getCurrentDirectory: () => root,
        getNewLine: () => "\n",
      }));
      writeFileSync(path.slice(0, -3) + ".js", result.outputText);
      rmSync(path);
    }
  }
}

function rewriteEntrypoints(value) {
  if (typeof value === "string") return value.replace(/\.ts$/, ".js");
  if (Array.isArray(value)) return value.map(rewriteEntrypoints);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, rewriteEntrypoints(item)]));
  return value;
}

function prepareHeadless(runtime, ts) {
  const modules = join(runtime, "node_modules");
  for (const name of extensionPackages) {
    const root = join(modules, name);
    compilePackage(root, ts);
    const path = join(root, "package.json");
    const pkg = JSON.parse(readFileSync(path, "utf8"));
    for (const key of ["main", "exports", "pi"]) {
      if (pkg[key] !== undefined) pkg[key] = rewriteEntrypoints(pkg[key]);
    }
    if (name === "@dataforxyz/agent-intercom-pi") delete pkg.dependencies.tsx;
    writeFileSync(path, JSON.stringify(pkg, null, 2) + "\n");
  }
  const spawnPath = join(modules, "@dataforxyz/agent-intercom-pi/broker/spawn.js");
  const spawn = readFileSync(spawnPath, "utf8");
  if (!spawn.includes('"broker.ts"')) throw new Error("intercom broker entry point changed");
  writeFileSync(spawnPath, spawn.replace('"broker.ts"', '"broker.js"'));
  const configPath = join(modules, "@dataforxyz/agent-intercom-pi/config.js");
  const config = readFileSync(configPath, "utf8");
  if (!config.includes('brokerCommand: "npx"') || !config.includes('brokerArgs: ["--no-install", "tsx"]'))
    throw new Error("intercom default launch configuration changed");
  writeFileSync(configPath, config.replace('brokerCommand: "npx"', 'brokerCommand: "node"').replace('brokerArgs: ["--no-install", "tsx"]', "brokerArgs: []"));
  for (const relative of bedrockModules) {
    const path = join(modules, relative);
    const source = readFileSync(path, "utf8");
    if (!source.includes("@aws-sdk/client-bedrock-runtime")) throw new Error(`Bedrock implementation changed: ${relative}`);
    writeFileSync(path, 'export function stream() { throw new Error("Amazon Bedrock is unavailable in pi-headless-usr; use the full profile"); }\nexport const streamSimple = stream;\n');
  }
  for (const name of removedPackages) rmSync(join(modules, name), { recursive: true });
  const aiManifest = join(modules, "@earendil-works/pi-ai/package.json");
  const ai = JSON.parse(readFileSync(aiManifest, "utf8"));
  delete ai.dependencies["@aws-sdk/client-bedrock-runtime"];
  delete ai.dependencies["@smithy/node-http-handler"];
  writeFileSync(aiManifest, JSON.stringify(ai, null, 2) + "\n");
  rmSync(join(modules, ".bin/tsx"));
  rmSync(join(modules, ".bin/esbuild"));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [runtime, compiler] = process.argv.slice(2);
  if (!runtime || !compiler) throw new Error("usage: node tools/headless.mjs RUNTIME TYPESCRIPT_MODULE");
  const { default: ts } = await import(pathToFileURL(resolve(compiler)).href);
  prepareHeadless(resolve(runtime), ts);
}
