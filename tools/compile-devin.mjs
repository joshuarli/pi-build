import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";
import { compilePackage } from "./headless.mjs";

const [rootArg, compilerArg] = process.argv.slice(2);
if (!rootArg || !compilerArg)
  throw new Error("usage: node tools/compile-devin.mjs PACKAGE_ROOT TYPESCRIPT_MODULE");
const root = resolve(rootArg);
const manifest = join(root, "package.json");
const pkg = JSON.parse(readFileSync(manifest, "utf8"));
if (pkg.name !== "pi-devin-local" || pkg.pi?.extensions?.length !== 1 ||
    pkg.pi.extensions[0] !== "./extensions/index.ts")
  throw new Error("Unexpected pinned Devin package or extension entrypoint");
const { default: ts } = await import(pathToFileURL(resolve(compilerArg)).href);
compilePackage(root, ts);
pkg.pi.extensions = ["./extensions/index.js"];
writeFileSync(manifest, JSON.stringify(pkg, null, 2) + "\n");
if (!existsSync(join(root, "extensions/index.js")) || !existsSync(join(root, "src/stream.js")))
  throw new Error("Devin provider compilation produced no runtime modules");
