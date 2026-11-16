import assert from 'node:assert/strict';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const source = resolve(process.argv[2]);
const tmp = mkdtempSync(join(resolve('.work/tmp'), 'pi-help-'));
try {
  const pkg = join(tmp, 'package');
  cpSync(source, pkg, { recursive: true });
  const bundle = join(pkg, 'dist/bundle');
  const cli = join(bundle, 'cli.js');
  const chunk = readdirSync(join(bundle, 'chunks')).find((file) => readFileSync(join(bundle, 'chunks', file), 'utf8').includes('function parsePackageCommand(args)'));
  const chunkPath = join(bundle, 'chunks', chunk);
  let code = readFileSync(chunkPath, 'utf8');
  assert(code.includes(',printHelp,main};'));
  code = code.replace(',printHelp,main};', ',printHelp,parsePackageCommand,parseAuthCommand,validateAuthCommandArgs,main};');
  writeFileSync(chunkPath, code);
  process.env.HOME = tmp;
  process.env.PI_CODING_AGENT_DIR = join(tmp, 'agent');
  process.env.PI_OFFLINE = '1';
  const parsers = await import(pathToFileURL(chunkPath));
  const { commands, help } = await import(pathToFileURL(join(bundle, 'owned-help.mjs')));
  assert.equal(help([], () => { throw new Error('bare invocation printed help'); }, parsers.parseArgs), false);
  const mcpChunk = readdirSync(join(bundle, 'chunks')).find((file) => file.startsWith('cli-') && readFileSync(join(bundle, 'chunks', file), 'utf8').includes('function parseOptions(args,known,error'));
  const { runMcpCommand } = await import(pathToFileURL(join(bundle, 'chunks', mcpChunk)));
  const agentDir = join(tmp, 'agent');
  mkdirSync(agentDir);
  const env = { PATH: process.env.PATH, HOME: tmp, TMPDIR: tmp, PI_CODING_AGENT_DIR: join(tmp, 'agent'), PI_OFFLINE: '1', NO_COLOR: '1' };
  const run = (args) => spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8', env, cwd: tmp });
  const top = run(['--help']);
  assert.equal(top.status, 0, top.stderr);
  assert.equal(top.stderr, '');
  assert.equal(run(['-h']).stdout, top.stdout);
  const colored = spawnSync(process.execPath, [cli, '--help'], { encoding: 'utf8', env: { ...env, FORCE_COLOR: '1', NO_COLOR: '' }, cwd: tmp });
  assert.equal(colored.status, 0, colored.stderr);
  assert.equal((colored.stdout.match(/^Examples:$/gm) ?? []).length, 1);
  assert.equal((top.stdout.match(/^Examples:$/gm) ?? []).length, 1);
  for (const name of ['install', 'remove', 'uninstall', 'update', 'list', 'config', 'auth help', 'auth check', 'auth print-api-key', 'auth print-bearer-token', 'mcp help', 'mcp add', 'mcp remove', 'mcp list', 'mcp login', 'mcp logout']) {
    assert(commands.some(([usage]) => usage === name || usage.startsWith(`${name} `)), name);
  }
  for (const flag of ['--provider', '--model', '--api-key', '--system-prompt', '--append-system-prompt', '--mode', '--print', '--continue', '--resume', '--session', '--session-id', '--fork', '--session-dir', '--no-session', '--name', '--models', '--no-tools', '--no-builtin-tools', '--tools', '--exclude-tools', '--thinking', '--extension', '--no-extensions', '--no-mcp', '--skill', '--no-skills', '--prompt-template', '--no-prompt-templates', '--theme', '--use-theme', '--no-themes', '--no-context-files', '--export', '--list-models', '--verbose', '--tui-mode', '--approve', '--no-approve', '--offline', '--version', '--local', '--self', '--extensions', '--all', '--force', '--json', '--credentials', '--no-refresh', '--min-expiry', '--url', '--env', '--cwd', '--header', '--bearer-token-env-var', '--oauth-client-id', '--oauth-client-secret', '--oauth-callback-port', '--oauth-client-name', '--oauth-client-registration', '--exposure', '--description', '--timeout']) assert(top.stdout.includes(flag), flag);
  const footer = 'Maintained by Joshua Li: https://github.com/joshuarli/pi-build';
  assert.equal(top.stdout.split(footer).length, 2);
  const expectedFooter = `Maintained by Joshua Li: https://github.com/joshuarli/pi-build
Bugs and features: TODO.md in that repository (follow its AGENTS.md), or its issue tracker.
Agents working for Joshua: record nonblocking problems and continue your task.
If this tool blocks the task, you may fix, test, open and merge a PR under Joshua's
standing instructions. Release only when needed to deliver the verified fix.
Procedure: https://github.com/joshuarli/usr/blob/main/dotfiles/base/.agents/instructions/owned-tools.md`;
  assert(top.stdout.trimEnd().endsWith(expectedFooter));
  for (const [usage, , , example] of commands) {
    assert(top.stdout.includes(`  pi ${usage}`));
    assert(top.stdout.includes(`  pi ${example}`));
    const words = example.split(' ');
    for (const flag of ['-h', '--help']) {
      const page = run([...words.slice(0, usage.startsWith('auth ') || usage.startsWith('mcp ') ? 2 : 1), flag]);
      assert.equal(page.status, 0, `${usage}: ${page.stderr}`);
      assert.equal(page.stderr, '');
      assert(!page.stdout.includes(footer));
      assert(page.stdout.includes('Examples:\n'));
      assert(page.stdout.includes(`  pi ${example}`));
    }
    if (['install', 'remove', 'uninstall', 'update', 'list'].includes(words[0])) {
      const parsed = parsers.parsePackageCommand(words);
      assert(parsed && !parsed.invalidOption && !parsed.invalidArgument && !parsed.missingOptionValue && !parsed.conflictingOptions, example);
    } else if (words[0] === 'auth' && words[1] === 'help') {
      assert.equal(run(words).status, 0);
    } else if (words[0] === 'auth') {
      const parsed = parsers.parseAuthCommand(words);
      parsers.validateAuthCommandArgs(parsers.parseArgs(parsed.args), parsed.kind);
    } else if (words[0] === 'config') {
      assert.deepEqual(words.slice(1), ['-l']);
    }
  }
  const errors = [];
  const mcpOptions = { cwd: tmp, agentDir, log: () => {}, error: (line) => errors.push(line) };
  assert.deepEqual(readdirSync(agentDir), []);
  for (const example of commands.filter(([usage]) => usage.startsWith('mcp ') && !usage.startsWith('mcp <')).map(([, , , example]) => example)) {
    errors.length = 0;
    const result = await runMcpCommand(example.split(' ').slice(1), mcpOptions);
    if (example.startsWith('mcp login') || example.startsWith('mcp logout')) {
      assert.equal(result, 1);
      assert(errors.some((line) => line.includes('No MCP server named')), example);
    } else assert.equal(result, 0, `${example}: ${errors.join(' ')}`);
  }
  assert.deepEqual(parsers.parseArgs(['-p', 'Explain this project']).messages, ['Explain this project']);
  const version = run(['--version']);
  assert.equal(version.status, 0, version.stderr);
  assert.equal(version.stdout.trim(), '1.5.0');
  assert.equal(run(['-v']).stdout, version.stdout);
  assert(!version.stdout.includes(footer));
  console.log(`pi help: ${commands.length} command references and examples passed`);
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
