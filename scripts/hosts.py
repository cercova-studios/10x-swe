#!/usr/bin/env python3
"""Per-host adapters generated from one canonical source.

Canonical source of truth:
  .claude-plugin/marketplace.json          marketplace name, owner, plugin list
  plugins/<plugin>/.claude-plugin/plugin.json  plugin name, version, description
  plugins/<plugin>/{skills,agents,commands}    components and their frontmatter

Generated (never edit by hand; run `scripts/hosts.py sync`):
  .agents/plugins/marketplace.json         OpenAI Codex repo marketplace
  plugins/<plugin>/.codex-plugin/plugin.json   Codex plugin overlay
  package.json                             pi package manifest (skills + prompts)
  plugins/10x-swe/{package.json,opencode-data.json}  OpenCode npm adapter
  the skill-requirements table in plugins/<plugin>/README.md (from each skill's
  `compatibility` field) and marketplace descriptions

The hand-written catalog in plugins/10x-swe/README.md stays the human index;
tests/test_plugin_metadata.py checks that it links every skill, agent and command.

Claude Code, Grok Build and GitHub Copilot CLI read the canonical
.claude-plugin files directly (.github/plugin/marketplace.json is a symlink).

Commands:
  sync              rewrite generated files
  check             fail if generated files are stale
  link HOST --dest DIR [--plugin NAME ...] [--unlink]
                    symlink skills (and translated agents/commands where the
                    host supports them) into a host's discovery directory.
                    HOST is one of: agents, opencode, pi
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / '.claude-plugin/marketplace.json'
BEGIN = '<!-- BEGIN GENERATED REQUIREMENTS: scripts/hosts.py sync -->'
END = '<!-- END GENERATED REQUIREMENTS -->'
CODEX_CATEGORY = {'10x-swe': 'Coding', 'knowledge': 'Productivity'}
# Claude Code agent colors -> opencode theme colors (opencode rejects other names).
OPENCODE_COLORS = {'red': 'error', 'orange': 'warning', 'yellow': 'warning', 'green': 'success',
                   'blue': 'info', 'cyan': 'info', 'purple': 'secondary', 'pink': 'accent'}


# ---------------------------------------------------------------- frontmatter
def split_frontmatter(text):
    if not text.startswith('---\n'):
        return None, text
    end = text.find('\n---\n', 4)
    if end < 0:
        raise ValueError('unterminated frontmatter')
    return text[4:end], text[end + 5:]


def parse_frontmatter(path):
    """Parse YAML frontmatter strictly (PyYAML) and return (data, body)."""
    raw, body = split_frontmatter(path.read_text(encoding='utf-8'))
    if raw is None:
        return {}, body
    try:
        import yaml
    except ImportError:
        sys.exit('PyYAML is required: python3 -m pip install PyYAML (or run with uv run --with pyyaml)')
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f'{path}: frontmatter is not a mapping')
    return data, body


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump_json(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + '\n'


# ---------------------------------------------------------------- inventory
def plugins():
    market = load_json(MARKETPLACE)
    result = []
    for entry in market['plugins']:
        root = (ROOT / entry['source']).resolve()
        manifest = load_json(root / '.claude-plugin/plugin.json')
        result.append({'entry': entry, 'root': root, 'manifest': manifest})
    return market, result


def components(root):
    skills = sorted(p.parent for p in (root / 'skills').glob('*/SKILL.md'))
    agents = sorted((root / 'agents').glob('*.md')) if (root / 'agents').is_dir() else []
    commands = sorted((root / 'commands').glob('*.md')) if (root / 'commands').is_dir() else []
    return skills, agents, commands


def first_sentence(text, limit=140):
    text = re.sub(r'\s+', ' ', str(text)).strip()
    match = re.match(r'(.+?[.!?])(\s|$)', text)
    sentence = match.group(1) if match else text
    if len(sentence) > limit:
        sentence = sentence[:limit - 1].rsplit(' ', 1)[0] + '…'
    return sentence.replace('|', '\\|')


# ---------------------------------------------------------------- generators
def codex_marketplace(market, items):
    return {
        'name': market['name'],
        'interface': {'displayName': market['name']},
        'plugins': [{
            'name': item['entry']['name'],
            'source': {'source': 'local', 'path': item['entry']['source']},
            'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
            'category': CODEX_CATEGORY.get(item['entry']['name'], 'Coding'),
        } for item in items],
    }


def codex_plugin(item):
    manifest = item['manifest']
    out = {key: manifest[key] for key in ('name', 'version', 'description', 'author', 'homepage',
                                          'repository', 'license', 'keywords') if key in manifest}
    out['skills'] = './skills/'
    out['interface'] = {
        'displayName': manifest['name'],
        'shortDescription': manifest['description'],
        'developerName': manifest.get('author', {}).get('name', ''),
        'category': CODEX_CATEGORY.get(manifest['name'], 'Coding'),
        'websiteURL': manifest.get('repository', ''),
    }
    return out


def pi_package(market, items):
    primary = next(item for item in items if item['entry']['name'] == market['name'])
    skills, prompts = [], []
    for item in items:
        rel = item['root'].relative_to(ROOT).as_posix()
        if (item['root'] / 'skills').is_dir():
            skills.append(f'./{rel}/skills')
        if (item['root'] / 'commands').is_dir():
            prompts.append(f'./{rel}/commands')
    return {
        'name': market['name'],
        'version': primary['manifest']['version'],
        'private': True,
        'description': market['description'],
        'license': primary['manifest'].get('license', 'MIT'),
        'repository': primary['manifest'].get('repository', ''),
        'keywords': ['pi-package'],
        'pi': {'skills': skills, 'prompts': prompts},
    }


def requirements(item):
    """Table of skills that need an account, API key or external tool (from `compatibility`)."""
    rows = []
    for folder in components(item['root'])[0]:
        data, _ = parse_frontmatter(folder / 'SKILL.md')
        if data.get('compatibility'):
            rel = (folder / 'SKILL.md').relative_to(item['root']).as_posix()
            rows.append(f"| [{folder.name}]({rel}) | {first_sentence(data['compatibility'], 240)} |")
    lines = [BEGIN, '']
    if rows:
        lines += ['## Skills that need accounts, keys or external tools', '',
                  'Every other skill runs with only your agent and the tools your task already uses.', '',
                  '| Skill | Needs |', '|---|---|', *rows, '']
    lines.append(END)
    return '\n'.join(lines)


def opencode_package(item):
    manifest = item['manifest']
    return {
        'name': '@cercova-studios/10x-swe', 'version': manifest['version'],
        'description': manifest['description'], 'license': manifest['license'],
        'repository': manifest['repository'], 'type': 'module',
        'exports': {'.': './index.js'},
        'files': ['index.js', 'opencode-data.json', 'skills', 'agents', 'commands', 'LICENSE'],
        'engines': {'node': '>=22', 'opencode': '>=2.0.32 <3'},
        'publishConfig': {'access': 'public'},
    }


def opencode_data(item):
    skills, agents, commands = components(item['root'])
    result = {'skills': [], 'agents': [], 'commands': []}
    for folder in skills:
        data, _ = parse_frontmatter(folder / 'SKILL.md')
        result['skills'].append({
            'id': data['name'], 'name': data['name'], 'description': data['description'],
            'path': (folder / 'SKILL.md').relative_to(item['root']).as_posix(),
            'autoinvoke': data.get('disable-model-invocation') is not True,
        })
    for kind, paths in [('agents', agents), ('commands', commands)]:
        for path in paths:
            data, body = parse_frontmatter(path)
            result[kind].append({'name': path.stem, 'description': data['description'],
                                 'content': body.lstrip('\n')})
    return result


def render_readme(path, block):
    text = path.read_text(encoding='utf-8')
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return head + block + tail
    return None  # README without markers: nothing generated


def expected():
    market, items = plugins()
    files = {ROOT / '.agents/plugins/marketplace.json': dump_json(codex_marketplace(market, items)),
             ROOT / 'package.json': dump_json(pi_package(market, items))}
    new_market = json.loads(json.dumps(market))
    for entry, item in zip(new_market['plugins'], items):
        entry['description'] = item['manifest']['description']
    files[MARKETPLACE] = dump_json(new_market)
    for item in items:
        files[item['root'] / '.codex-plugin/plugin.json'] = dump_json(codex_plugin(item))
        if item['entry']['name'] == '10x-swe':
            files[item['root'] / 'package.json'] = dump_json(opencode_package(item))
            files[item['root'] / 'opencode-data.json'] = dump_json(opencode_data(item))
        readme = item['root'] / 'README.md'
        rendered = render_readme(readme, requirements(item))
        if rendered is not None:
            files[readme] = rendered
    return files, items


# ---------------------------------------------------------------- checks
def sync(check):
    files, _ = expected()
    errors = []
    for path, content in files.items():
        current = path.read_text(encoding='utf-8') if path.exists() else None
        if current != content:
            if check:
                errors.append(f'{path.relative_to(ROOT)} is stale; run: python3 scripts/hosts.py sync')
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
                print('wrote', path.relative_to(ROOT))
    for error in errors:
        print('ERROR:', error, file=sys.stderr)
    if not errors and check:
        print(f'OK: {len(files)} generated files match their canonical sources')
    return 1 if errors else 0


# ---------------------------------------------------------------- link
LAYOUT = {
    # host: (skills subdir, commands subdir or None, agents subdir or None)
    'agents': ('skills', None, None),        # .agents/ : Codex, opencode, pi, Grok, Copilot
    'opencode': ('skills', 'commands', 'agents'),  # .opencode/ or ~/.config/opencode/
    'pi': ('skills', 'prompts', None),       # .pi/ or ~/.pi/agent/
}


def opencode_agent(path):
    data, body = parse_frontmatter(path)
    lines = ['---', 'description: ' + json.dumps(str(data['description']), ensure_ascii=False), 'mode: subagent']
    color = OPENCODE_COLORS.get(str(data.get('color', '')).lower())
    if color:
        lines.append('color: ' + color)
    lines += ['---', f'<!-- Generated by 10x-swe scripts/hosts.py from {path}. '
              'Model is inherited from the invoking agent. -->', '']
    return '\n'.join(lines) + body.lstrip('\n')


def owned_by_repo(path, source, agent):
    if path.is_symlink():
        return source is not None and Path(os.path.realpath(path)) == source.resolve()
    if agent is not None and path.is_file():
        return f'<!-- Generated by 10x-swe scripts/hosts.py from {agent}. ' in path.read_text(errors='replace')
    return False


def place(target, *, link_to=None, content=None, agent=None, dry_run=False):
    if target.exists() or target.is_symlink():
        if not owned_by_repo(target, link_to, agent):
            raise SystemExit(f'Refusing to replace {target}: it is not managed by this repository')
        if not dry_run:
            target.unlink()
    print(('would link ' if dry_run else 'linked ') + str(target))
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if link_to is not None:
        target.symlink_to(link_to, target_is_directory=link_to.is_dir())
    else:
        target.write_text(content, encoding='utf-8')


def link(host, dest, selected, unlink, dry_run):
    skills_dir, commands_dir, agents_dir = LAYOUT[host]
    dest = dest.expanduser().absolute()
    _, items = plugins()
    names = {item['entry']['name'] for item in items}
    unknown = set(selected) - names
    if unknown:
        raise SystemExit('Unknown plugin(s): ' + ', '.join(sorted(unknown)))
    seen = {}
    plan = []
    for item in items:
        if item['entry']['name'] not in selected:
            continue
        skills, agents, commands = components(item['root'])
        planned = [(dest / skills_dir / folder.name, folder, None) for folder in skills]
        if commands_dir:
            planned += [(dest / commands_dir / path.name, path, None) for path in commands]
        if agents_dir:
            planned += [(dest / agents_dir / path.name, None, path) for path in agents]
        for target, source, agent in planned:
            if target in seen:
                raise SystemExit(f'Name collision at {target} between {seen[target]} and {source or agent}')
            seen[target] = source or agent
            for directory in (dest, target.parent):
                if directory.is_symlink():
                    raise SystemExit(f'Refusing symlinked host directory: {directory}')
                if directory.exists() and not directory.is_dir():
                    raise SystemExit(f'Host directory is not a directory: {directory}')
            if not unlink and (target.exists() or target.is_symlink()) and not owned_by_repo(target, source, agent):
                raise SystemExit(f'Refusing to replace {target}: it is not managed by this repository')
            content = opencode_agent(agent) if agent is not None and not unlink else None
            plan.append((target, source, agent, content))
    for target, source, agent, content in plan:
        if unlink:
            if (target.exists() or target.is_symlink()) and owned_by_repo(target, source, agent):
                print(('would remove ' if dry_run else 'removed ') + str(target))
                if not dry_run:
                    target.unlink()
        else:
            place(target, link_to=source, content=content, agent=agent, dry_run=dry_run)
    return 0


def main():
    parser = argparse.ArgumentParser(prog='scripts/hosts.py', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('sync', help='rewrite generated adapter files and catalogs')
    sub.add_parser('check', help='fail when generated files are stale')
    linker = sub.add_parser('link', help="link skills into a host's discovery directory")
    linker.add_argument('host', choices=sorted(LAYOUT))
    linker.add_argument('--dest', type=Path, required=True,
                        help='host directory, e.g. ./.agents, ~/.agents, ./.opencode, ~/.config/opencode, ./.pi, ~/.pi/agent')
    linker.add_argument('--plugin', action='append', default=None,
                        help='plugin to link (repeatable; default: 10x-swe)')
    linker.add_argument('--unlink', action='store_true', help='remove links this script created')
    linker.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.command in ('sync', 'check'):
        return sync(check=args.command == 'check')
    return link(args.host, args.dest, args.plugin or ['10x-swe'], args.unlink, args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
