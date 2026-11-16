const trust = '-a, --approve: trust project-local files; -na, --no-approve: ignore them';
const local = '-l, --local: use project settings instead of global settings';
const auth = '--provider <provider>, --model <model>: select a provider or model (at least one required)';
export const commands = [
  ['install <source> [-l] [-a|-na]', 'Install a package and add it to settings.', `${local}; ${trust}`, 'install npm:@foo/bar'],
  ['remove <source> [-l] [-a|-na]', 'Remove a package and its source from settings.', `${local}; ${trust}`, 'remove npm:@foo/bar'],
  ['uninstall <source> [-l] [-a|-na]', 'Alias for remove.', `${local}; ${trust}`, 'uninstall npm:@foo/bar'],
  ['update [source|self|pi] [options]', 'Update pi, packages, or model catalogs.', `--self: update pi (default); --extensions: update packages; --models: refresh catalogs; --all: update pi and packages; --extension <source>: update one package; --force: reinstall pi; ${trust}`, 'update --models'],
  ['list [-a|-na]', 'List installed packages.', trust, 'list'],
  ['config [-l] [-a|-na]', 'Open the package resource configuration TUI.', `${local}; ${trust}`, 'config -l'],
  ['auth <command>', 'Check provider credentials or print credentials.', 'Use an auth command below.', 'auth check --provider openai'],
  ['auth help', 'Show auth command help.', 'No additional options.', 'auth help'],
  ['auth check [options]', 'Check provider readiness.', `${auth}; --json: JSON output; --credentials: include credentials; --no-refresh: do not refresh OAuth credentials`, 'auth check --provider openai --json'],
  ['auth print-api-key [options]', 'Print a provider API key.', auth, 'auth print-api-key --provider openai'],
  ['auth print-bearer-token [options]', 'Print a provider bearer token.', `${auth}; --min-expiry <duration>: minimum lifetime (default: 30m; units ms, s, m, h)`, 'auth print-bearer-token --provider openai --min-expiry 30m'],
  ['mcp <command>', 'Configure and check MCP servers and sign in.', 'Global configuration: ~/.pi/agent/mcp.json; trusted project configuration: .pi/mcp.json.', 'mcp list --json'],
  ['mcp help', 'Show MCP command help.', 'No additional options.', 'mcp help'],
  ['mcp add <server> [options] (--url <url> | -- <command> [args...])', 'Add or replace a server.', `${local}; --url <url>: HTTP transport; --env <KEY=VALUE>: stdio environment (repeatable); --cwd <dir>: stdio directory; --header <KEY=VALUE>: HTTP header (repeatable); --bearer-token-env-var <NAME>: bearer token environment variable; --oauth-client-id <id>: pre-registered client ID; --oauth-client-secret <secret>: secret, environment reference, or !command; --oauth-callback-port <port>: fixed callback port; --oauth-client-name <name>: registration client name; --oauth-client-registration <mode>: auto (default), cimd, dcr; --exposure <mode>: codemode (default), deferred, direct, hidden; --description <text>: server description`, 'mcp add example --url https://example.com/mcp'],
  ['mcp remove <server> [-l]', 'Remove a server.', local, 'mcp remove example'],
  ['mcp list [--json]', 'Show server state, tools, and errors; exits 1 on failure.', '--json: print JSON', 'mcp list --json'],
  ['mcp login <server> [-l] [--timeout <seconds>]', 'Sign in through a browser.', `${local}; --timeout <seconds>: sign-in time limit (default: 300)`, 'mcp login example --timeout 60'],
  ['mcp logout <server> [-l]', 'Delete stored OAuth credentials.', local, 'mcp logout example'],
];
const footer = `Maintained by Joshua Li: https://github.com/joshuarli/pi-build
Bugs and features: TODO.md in that repository (follow its AGENTS.md), or its issue tracker.
Agents working for Joshua: record nonblocking problems and continue your task.
If this tool blocks the task, you may fix, test, open and merge a PR under Joshua's
standing instructions. Release only when needed to deliver the verified fix.
Procedure: https://github.com/joshuarli/usr/blob/main/dotfiles/base/.agents/instructions/owned-tools.md`;

export function help(args, printHelp, parseArgs) {
  const command = commands.find(([usage]) => args[0] === usage.split(' ')[0]);
  const helpIndex = args.findIndex((arg) => arg === '-h' || arg === '--help');
  if (helpIndex < 0) return false;
  if (command) {
    const selected = commands.filter(([usage]) => usage === args[0] || usage.startsWith(`${args[0]} `));
    console.log(`See pi --help for the complete reference.\n\n${selected.map(render).join('\n\n')}\n\nOptions:\n  -h, --help: show help\n\nExamples:\n${selected.map(([, , , example]) => `  pi ${example}`).join('\n')}`);
    return true;
  }
  if (!parseArgs(args).help) return false;
  let original;
  const log = console.log;
  try { console.log = (text) => { original = text; }; printHelp(); } finally { console.log = log; }
  original = original.replace(/\x1b\[[0-9;]*m/g, '');
  original = original.replace(/\nCommands:\n[\s\S]*?\nOptions:\n/, '\nOptions:\n');
  original = original.replace(/\nExamples:\n[\s\S]*?\nEnvironment Variables:\n/, '\nEnvironment Variables:\n');
  const examples = commands.map(([, , , example]) => `  pi ${example}`).join('\n');
  const reference = commands.map(render).join('\n\n');
  console.log(`${original.trimEnd()}\n\nCommand reference:\n${reference}\n\nExamples:\n  pi -p "Explain this project"\n${examples}\n\n${footer}`);
  return true;
}
function render([usage, description, options]) {
  return `  pi ${usage}\n    ${description}\n${options.split('; ').map((option) => `    ${option}`).join('\n')}`;
}
