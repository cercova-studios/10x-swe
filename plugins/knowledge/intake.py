"""Bounded existing-skill inspection. Source files are data and stay unchanged."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import re
import subprocess
import sys
import tempfile

import yaml

MAX_SKILLS = 2048
MAX_FILE = 4 * 1024 * 1024
MAX_BUNDLE = 64 * 1024 * 1024
SKIP = {'.git', '__pycache__', 'node_modules', 'target', '.venv'}


def paths(root, ancestors=frozenset(), budget=None):
    budget = [0] if budget is None else budget
    budget[0] += 1
    if budget[0] > 16384 or len(ancestors) > 64:
        raise ValueError('directory traversal budget exceeded')
    real = root.resolve(strict=True)
    if real in ancestors:
        raise ValueError('directory alias cycle: ' + str(root))
    if not real.is_dir():
        raise ValueError('skill root is not a directory: ' + str(root))
    if (root / 'SKILL.md').is_file():
        yield root / 'SKILL.md'
        return
    for child in sorted(root.iterdir()):
        if child.name.startswith('.') or child.name in SKIP:
            continue
        if child.is_dir():
            yield from paths(child, ancestors | {real}, budget)
        elif child.is_symlink() and not child.exists():
            raise ValueError('broken directory alias: ' + str(child))


def metadata(path):
    with path.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('SKILL.md exceeds 1 MiB')
    text = raw.decode('utf8')
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != '---':
        raise ValueError('missing frontmatter')
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
    if end is None:
        raise ValueError('unterminated frontmatter')
    header = ''.join(lines[1:end])
    depth = 0
    for count, event in enumerate(yaml.parse(header)):
        if isinstance(event, yaml.events.AliasEvent) or count > 8192:
            raise ValueError('untrusted YAML aliases/node budget rejected')
        if isinstance(event, (yaml.events.SequenceStartEvent, yaml.events.MappingStartEvent)):
            depth += 1
        elif isinstance(event, (yaml.events.SequenceEndEvent, yaml.events.MappingEndEvent)):
            depth -= 1
        if depth > 32:
            raise ValueError('frontmatter nesting budget exceeded')
    data = yaml.safe_load(header)
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) and data[k].strip()
                                          for k in ('name', 'description')):
        raise ValueError('name and description must be nonempty strings')
    if len(data['name']) > 256 or len(data['description']) > 8192:
        raise ValueError('metadata exceeds name/description limits')
    return data, ''.join(lines[end + 1:]), hashlib.sha256(raw).hexdigest()


def bundle(folder):
    files, issues, size = {}, [], 0
    for base, directories, names in os.walk(folder, followlinks=False):
        for directory in directories:
            if directory.startswith('.') and directory not in SKIP:
                issues.append('omitted hidden resource directory: ' + str((Path(base)/directory).relative_to(folder)))
        directories[:] = sorted(d for d in directories if d not in SKIP and not d.startswith('.'))
        for name in list(directories):
            path = Path(base) / name
            if path.is_symlink():
                issues.append('unfollowed resource directory alias: ' + str(path.relative_to(folder)))
                directories.remove(name)
        for name in sorted(names):
            if name.endswith('.pyc') or name == '.DS_Store':
                continue
            path = Path(base) / name
            rel = str(path.relative_to(folder))
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                issues.append('nonregular resource: ' + rel)
                continue
            if info.st_size > MAX_FILE or size + info.st_size > MAX_BUNDLE:
                issues.append('resource byte budget exceeded: ' + rel)
                continue
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'rb') as stream:
                actual = os.fstat(stream.fileno())
                if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError('resource changed during inspection: ' + rel)
                raw = stream.read(MAX_FILE + 1)
            if len(raw) > MAX_FILE:
                issues.append('resource changed beyond budget: ' + rel)
                continue
            size += len(raw)
            files[rel] = {'sha256': hashlib.sha256(raw).hexdigest(),
                          'mode': stat.S_IMODE(info.st_mode), 'bytes': len(raw)}
            if len(files) > 4096:
                raise ValueError('bundle exceeds 4096 resources')
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return digest, files, issues


def inspect(roots):
    records, issues, seen = [], [], {}
    for label, root in roots:
        count = 0
        try:
            for path in paths(root):
                count += 1
                if len(records) >= MAX_SKILLS or count > MAX_SKILLS:
                    raise ValueError('inventory exceeds 2048 skills')
                try:
                    data, body, entry_hash = metadata(path)
                    digest, files, omissions = bundle(path.parent.resolve())
                    if files.get('SKILL.md', {}).get('sha256') != entry_hash:
                        raise ValueError('SKILL.md changed during inspection')
                    duplicate = seen.get(digest) if not omissions else None
                    identity = label + '/' + str(path.parent.relative_to(root))
                    if identity.endswith('/.'):
                        identity = label + '/' + path.parent.name
                    record = {'id': identity, 'name': data['name'], 'description': data['description'],
                              'path': str(path.absolute()), 'canonical_path': str(path.resolve()),
                              'entrypoint_sha256': entry_hash, 'bundle_sha256': digest,
                              'resource_count': len(files), 'words': len(body.split()),
                              'metadata': data.get('metadata', {}), 'resources': files,
                              'coverage': 'partial' if omissions else 'complete',
                              'limitations': omissions, 'duplicate_of': duplicate,
                              'trust': 'existing-unreviewed', 'execution_authority': False}
                    records.append(record)
                    if not omissions and not duplicate:
                        seen[digest] = identity
                except (OSError, ValueError, yaml.YAMLError) as error:
                    issues.append({'path': str(path), 'error': str(error)})
        except (OSError, ValueError) as error:
            issues.append({'root': str(root), 'error': str(error)})
    names = {}
    for record in records:
        names.setdefault(record['name'], []).append(record)
    conflicts = {name: [r['id'] for r in group] for name, group in names.items()
                 if len({r['bundle_sha256'] for r in group}) > 1}
    return {'schema': 'existing-skills/v1', 'skills': records, 'name_conflicts': conflicts,
            'issues': issues, 'coverage': 'partial' if issues or any(r['limitations'] for r in records) else 'complete',
            'policy': 'Read-only inventory. Duplicates and conflicts are data; no execution, approval, rewriting or activation.'}


def register(report, prefix):
    """Stage a complete graph before replacing the owned roots; never alter a skill."""
    import importlib.util
    helper = prefix / 'skills/skill-graph/scripts/graph.py'
    spec = importlib.util.spec_from_file_location('intake_graph', helper)
    graph = importlib.util.module_from_spec(spec); spec.loader.exec_module(graph)
    rootfile = prefix / 'knowledge/skills/roots.json'
    config = graph.read_json(rootfile)
    additions = []
    for record in report['skills']:
        if record['coverage'] != 'complete' or record['duplicate_of']:
            continue
        additions.append({'id': 'existing/' + record['id'], 'path': str(Path(record['canonical_path']).parent),
                          'read_only': True, 'namespace': 'existing/' + record['id'].split('/')[0]})
    replacing = {r['id'] for r in additions}
    config['roots'] = [r for r in config['roots'] if r['id'] not in replacing] + additions
    candidate = graph.inventory(config)
    errors = graph.check(candidate)
    if errors:
        raise ValueError('External graph registration failed; roots unchanged: ' + '; '.join(errors[:10]))
    for record in report['skills']:
        if record['coverage'] == 'complete':
            current, _, omissions = bundle(Path(record['canonical_path']).parent)
            if omissions or current != record['bundle_sha256']:
                raise ValueError('External bundle changed before registration: ' + record['id'])
    # Graph commands serialize publication with the graph lock; retain the old roots on failure.
    old = rootfile.read_bytes()
    with tempfile.TemporaryDirectory(prefix='knowledge-intake-') as stage:
        staged = Path(stage) / 'roots.json'
        staged.write_text(json.dumps(config))
        if rootfile.read_bytes() != old:
            raise ValueError('Registered roots changed concurrently')
        graph.write_graph(candidate, rootfile.parent, roots=config, expected_roots=old)
    result = subprocess.run([str(prefix/'bin/skill-search'), 'refresh', '--lexical'], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Graph registration published but catalog refresh failed; rerun refresh --lexical: ' + result.stderr)
    return [r['id'] for r in additions]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', required=True, help='SCOPE=/absolute/skills/root')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--index', action='store_true', help='Explicitly register complete bundles as read-only graph data')
    args = parser.parse_args()
    roots = []
    for value in args.root:
        label, separator, path = value.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', label):
            parser.error('roots require a stable SCOPE=/absolute/path')
        root = Path(path).expanduser().absolute()
        roots.append((label, root))
    report = inspect(roots)
    if args.index:
        if not os.environ.get('AGENT_KNOWLEDGE_HOME'):
            parser.error('--index requires an explicit AGENT_KNOWLEDGE_HOME installation')
        report['registered'] = register(report, Path(os.environ['AGENT_KNOWLEDGE_HOME']))
    result = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(result)
    else:
        print(result, end='')
    print('intake: %d skills, %d name conflicts, %d issues, coverage=%s%s'
          % (len(report.get('skills', [])), len(report.get('name_conflicts', {})),
             len(report.get('issues', [])), report.get('coverage'),
             ' -> ' + str(args.output) if args.output else ''), file=sys.stderr)
    return 2 if report['coverage'] != 'complete' else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
