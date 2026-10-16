#!/usr/bin/env python3
"""Local skill inventory, directed relationships and reversible rewrite plans."""
import argparse
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml
import orjson


def read_json(path):
    return orjson.loads(Path(path).read_bytes())


def json_text(value):
    return orjson.dumps(value, option=orjson.OPT_INDENT_2).decode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bounded(path, limit=1024 * 1024):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(str(path) + ': resource exceeds byte limit')
    return raw


def frontmatter(path):
    text = bounded(path).decode('utf-8')
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != '---':
        raise ValueError(f'{path}: missing frontmatter')
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
    if end is None:
        raise ValueError(f'{path}: unterminated frontmatter')
    header = ''.join(lines[1:end])
    depth = 0
    for count, event in enumerate(yaml.parse(header)):
        if isinstance(event, yaml.events.AliasEvent) or count > 8192:
            raise ValueError('frontmatter aliases/node budget rejected')
        if isinstance(event, (yaml.events.SequenceStartEvent, yaml.events.MappingStartEvent)):
            depth += 1
        elif isinstance(event, (yaml.events.SequenceEndEvent, yaml.events.MappingEndEvent)):
            depth -= 1
        if depth > 32:
            raise ValueError('frontmatter nesting budget exceeded')
    data = yaml.safe_load(header)
    if not isinstance(data, dict) or not isinstance(data.get('name'), str):
        raise ValueError(f'{path}: invalid skill metadata')
    metadata = data.get('metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError(f'{path}: metadata must be a map')
    return data, ''.join(lines[end + 1:])


def identifiers(value):
    if not isinstance(value, str):
        raise ValueError('graph metadata values must be strings')
    return sorted(set(x.strip() for x in value.split(',') if x.strip()))


def portable_links(data, field):
    """Top-level Obsidian list properties; links use scoped vault-root paths."""
    values = data.get(field, [])
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ValueError(field + ' must be a quoted Wikilink list')
    result=[]
    for value in values:
        if not value.startswith('[[') or not value.endswith(']]'):
            if field == 'references':
                continue  # Existing plain reference-topic metadata is not a graph declaration.
            raise ValueError(field + ': expected [[scoped/id/SKILL]]')
        target=value[2:-2].split('|',1)[0].split('#',1)[0].removesuffix('.md')
        if not target.endswith('/SKILL') or not valid_identity(target[:-6]):
            raise ValueError(field + ': invalid scoped note target')
        result.append(target[:-6])
    return sorted(set(result))


def skill_files(root):
    """Follow directory aliases with ancestor-cycle detection, not global suppression."""
    def walk(folder, ancestors):
        real = folder.resolve()
        if real in ancestors:
            raise ValueError(f'directory alias cycle: {folder}')
        if not folder.exists():
            raise ValueError(f'broken skill alias: {folder}')
        direct = folder / 'SKILL.md'
        if direct.is_file():
            yield direct
            return
        for child in sorted(folder.iterdir()):
            if child.name.startswith('.') or child.name == '__pycache__':
                continue
            if child.is_dir():
                yield from walk(child, ancestors | {real})
            elif child.is_symlink() and not child.exists():
                raise ValueError(f'broken alias: {child}')
    if not root.is_dir():
        raise ValueError(f'registered root missing: {root}')
    yield from walk(root, set())


def valid_identity(value):
    return (isinstance(value, str) and bool(value) and not any(c.isspace() for c in value)
            and not Path(value).is_absolute() and all(p not in {'', '.', '..'} for p in value.split('/')))


def fingerprint(folder):
    files = {}
    for base, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {'.git', '__pycache__'})
        for name in sorted(names):
            if name.endswith('.pyc'):
                continue
            path = Path(base) / name
            relative = str(path.relative_to(folder))
            files[relative] = (('symlink:' + os.readlink(path)) if path.is_symlink()
                               else f'{path.stat().st_mode & 0o777:o}:' + digest(path.read_bytes()))
        for name in dirs:
            path = Path(base) / name
            if path.is_symlink():
                files[str(path.relative_to(folder))] = 'symlink:' + os.readlink(path)
    return digest(orjson.dumps(files, option=orjson.OPT_SORT_KEYS))


def inventory(config):
    nodes, canonical, aliases, errors = [], {}, [], []
    for root in config['roots']:
        folder = Path(root['path']).expanduser().absolute()
        try:
            paths = sorted(skill_files(folder), key=lambda p: (p.resolve() != folder.resolve() / p.relative_to(folder), str(p)))
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue
        for path in paths:
            real = path.resolve()
            if real in canonical:
                aliases.append({'id': root['id'] + '/' + str(path.parent.relative_to(folder)),
                                'path': str(path), 'target': canonical[real]})
                continue
            try:
                data, body = frontmatter(path)
                metadata = data.get('metadata', {})
                external = root.get('read_only', False)
                relative = str(path.parent.relative_to(folder))
                scoped = root['id'] if relative == '.' else root['id'] + '/' + relative
                identity = scoped if external else metadata.get('skill-graph-id') or scoped
                if not valid_identity(identity):
                    raise ValueError('invalid graph identity')
                node = {'id': identity, 'kind': 'skill', 'name': data['name'], 'scope': root['id'],
                        'path': str(real), 'discovery_path': str(path),
                        'description': str(data.get('description', '')),
                        'sha256': digest(path.read_bytes()), 'uses': identifiers(metadata.get('skill-graph-uses', '')),
                        'declared_used_by': identifiers(metadata.get('skill-graph-used-by', '')),
                        'body_links': re.findall(r'\]\(([^\s)]+)', body),
                        'legacy_related': metadata.get('related-skills', ''),
                        'workflows': identifiers(metadata.get('skill-graph-workflows', '')),
                        'portable': {field: portable_links(data,field) for field in ('uses','used-by','related','references','related-inferred')},
                        'wiki_body': re.findall(r'\[\[([^\]]+)\]\]', body)}
                if external:
                    node.update(read_only=True, trust='existing-unreviewed',
                                original_id=metadata.get('skill-graph-id', scoped),
                                import_namespace=root.get('namespace', root['id']),
                                unresolved_references=[], original_description=node['description'])
                    node['description'] = '[Existing skill; unreviewed] ' + node['description']
                if 'uses' in data:
                    if 'skill-graph-uses' in metadata and node['uses']!=node['portable']['uses']:
                        raise ValueError('uses property and canonical metadata disagree')
                    node['uses']=node['portable']['uses']
                    for target in node['uses']:
                        if not any(link.split('|',1)[0].split('#',1)[0].removesuffix('.md')==target+'/SKILL' for link in node['wiki_body']):
                            raise ValueError('uses property lacks matching direct body link: '+target)
                if 'used-by' in data:
                    node['declared_used_by']=node['portable']['used-by']
                nodes.append(node)
                canonical[real] = identity
            except (OSError, ValueError, yaml.YAMLError) as exc:
                errors.append(f'{path}: {exc}')
    # Workflow documents are owned resources, not skills or executable dependencies.
    owners = list(nodes)
    for owner in owners:
        directory = Path(owner['path']).parent
        for path in sorted((directory / 'workflows').glob('*.md')):
            try:
                if not path.read_bytes().startswith(b'---'):
                    continue  # Ordinary workflow prose is not a structured contract.
                data, _ = frontmatter(path)
                if data.get('schema') != 'workflow/v1':
                    continue
                if path.is_symlink() or not path.resolve().is_relative_to(directory):
                    raise ValueError('workflow escapes owner bundle')
                participants = data.get('skills')
                if not isinstance(participants, list) or not participants or not all(valid_identity(x) for x in participants):
                    raise ValueError('workflow requires scoped skill participants')
                resource_names = data.get('resources')
                if not isinstance(resource_names, list) or not resource_names:
                    raise ValueError('workflow resources must be a nonempty list')
                resources = {}
                for relative in resource_names:
                    if not valid_identity(relative):
                        raise ValueError('invalid workflow resource')
                    resource = directory / relative
                    if resource.is_symlink() or not resource.resolve().is_relative_to(directory):
                        raise ValueError('workflow resource escapes owner bundle')
                    resources[relative] = digest(bounded(resource))
                if not resources or data.get('runner') not in resources:
                    raise ValueError('workflow runner must be a retained resource')
                identity = owner['id'] + '/workflows/' + path.stem
                nodes.append(dict(id=identity, kind='workflow', name=data['name'], scope=owner['scope'],
                    path=str(path.resolve()), discovery_path=str(Path(owner['discovery_path']).parent/'workflows'/path.name),
                    description=str(data.get('description', '')), sha256=digest(path.read_bytes()),
                    owner=owner['id'], resources=resources, runner=data['runner'], participants=participants,
                    uses=[], used_by=[], declared_used_by=[], body_links=[], wiki_body=[], workflows=[],
                    portable={f: [] for f in ('related','references','related-inferred')}))
                if owner.get('read_only'):
                    nodes[-1].update(read_only=True, trust='existing-unreviewed',
                                     original_id=owner['original_id']+'/workflows/'+path.stem,
                                     import_namespace=owner['import_namespace'], unresolved_references=[])
                for alias in list(aliases):
                    if alias['target'] == owner['id']:
                        aliases.append(dict(id=alias['id']+'/workflows/'+path.stem,
                            path=str(Path(alias['path']).parent/'workflows'/path.name), target=identity))
            except (OSError, ValueError, yaml.YAMLError) as exc:
                errors.append(f'{path}: {exc}')
    # External inventories preserve source metadata and resolve names only in the derived graph.
    translations = {}
    for node in nodes:
        if node.get('read_only'):
            key = (node['import_namespace'], node['original_id'])
            translations.setdefault(key, []).append(node['id'])
    known = {node['id'] for node in nodes}
    for node in nodes:
        if not node.get('read_only'):
            continue
        def resolve(target):
            candidates = translations.get((node['import_namespace'], target), [])
            if len(candidates) == 1:
                return candidates[0]
            if not candidates and target in known:
                # An external declaration cannot rewrite owned generated backlinks.
                node['unresolved_references'].append(target)
                return None
            node['unresolved_references'].append(target)
            return None
        for field in ('uses', 'workflows', 'participants'):
            if field in node:
                node[field] = sorted({value for target in node[field] if (value := resolve(target))})
        for field in node['portable']:
            node['portable'][field] = sorted({value for target in node['portable'][field] if (value := resolve(target))})
        # Portable body references stay the original source text, never rewritten instructions.
        node['wiki_body'] = [target + '/SKILL' for field in node['portable']
                             for target in node['portable'][field]]
    by_id = {}
    for node in nodes:
        if node['id'] in by_id:
            errors.append('duplicate graph identity: ' + node['id'])
        by_id[node['id']] = node
    edges, candidates = [], []
    for node in nodes:
        node['used_by'] = []
    for node in nodes:
        for target in node.pop('workflows'):
            if target not in by_id or by_id[target].get('kind') != 'workflow':
                errors.append(f"{node['id']}: unresolved workflow {target}")
            else:
                edges.append(dict(source=node['id'], target=target, relation='associated_workflow'))
        for target in node.get('participants', []):
            if target not in by_id or by_id[target].get('kind') != 'skill':
                errors.append(f"{node['id']}: unresolved workflow participant {target}")
            else:
                edges.append(dict(source=node['id'], target=target, relation='uses_skill'))
        for target in node['uses']:
            if target not in by_id:
                errors.append(f"{node['id']}: unresolved target {target}")
            else:
                edges.append({'source': node['id'], 'target': target, 'relation': 'uses'})
                by_id[target]['used_by'].append(node['id'])
        for field in ('related','references','related-inferred'):
            for target in node['portable'][field]:
                if target not in by_id:
                    errors.append(f"{node['id']}: unresolved portable target {target}")
                elif not any(link.split('|',1)[0].split('#',1)[0].removesuffix('.md')==target+'/SKILL' for link in node['wiki_body']):
                    errors.append(f"{node['id']}: {field} lacks matching direct body link {target}")
                else:
                    edges.append({'source':node['id'],'target':target,'relation':'related' if field=='related-inferred' else field,
                                  'provenance':'frontmatter+body-link','status':'inferred' if field=='related-inferred' else 'declared'})
        for link in node.pop('body_links'):
            if '://' in link or link.startswith('#'):
                continue
            path = (Path(node['path']).parent / link.split('#')[0]).resolve()
            if path in canonical:
                candidates.append({'source': node['id'], 'target': canonical[path], 'relation': 'references', 'evidence': link})
        for link in node.pop('wiki_body'):
            target=link.split('|',1)[0].split('#',1)[0].removesuffix('.md').removesuffix('/SKILL')
            if target in by_id:
                candidates.append({'source':node['id'],'target':target,'relation':'references','evidence':'[['+link+']]'})
        node.pop('portable')
    for node in nodes:
        node['used_by'].sort()
        if node.get('read_only'):
            node['original_declared_used_by'] = node['declared_used_by']
            node['declared_used_by'] = list(node['used_by'])
    return {'schema': 1, 'roots': config['roots'], 'nodes': sorted(nodes, key=lambda n: n['id']),
            'aliases': aliases, 'edges': edges, 'candidates': candidates, 'errors': errors}


def check(graph, hashes=True):
    errors = list(graph['errors'])
    for node in graph['nodes']:
        if node['declared_used_by'] != node['used_by']:
            errors.append(f"{node['id']}: stale generated backlinks")
        if hashes:
            try:
                if digest(Path(node['path']).read_bytes()) != node['sha256']:
                    errors.append(f"{node['id']}: file changed; rebuild graph")
                if node.get('kind') == 'workflow':
                    owner = next(n for n in graph['nodes'] if n['id'] == node['owner'])
                    for relative, expected in node['resources'].items():
                        resource = Path(owner['path']).parent / relative
                        if resource.is_symlink() or not resource.resolve().is_relative_to(Path(owner['path']).parent) or digest(resource.read_bytes()) != expected:
                            errors.append(f"{node['id']}: resource changed; rebuild graph")
            except OSError:
                errors.append(f"{node['id']}: file missing; rebuild graph")
    if hashes:
        current = inventory({'roots': graph['roots']})
        errors.extend(current['errors'])
        recorded = {(n['id'], n['path'], n['discovery_path']) for n in graph['nodes']}
        observed = {(n['id'], n['path'], n['discovery_path']) for n in current['nodes']}
        if recorded != observed or graph['aliases'] != current['aliases']:
            errors.append('skill inventory or aliases changed; rebuild graph')
    return errors


def annotate(graph, declarations, output):
    """Only emit quarantine proposals, never mutate active skills."""
    output = Path(output)
    if output.exists():
        raise ValueError('annotation output must be fresh')
    nodes = {n['id']: n for n in graph['nodes']}
    uses = {n['id']: list(n['uses']) for n in graph['nodes']}
    for source, targets in declarations.items():
        if not isinstance(targets, list) or source not in nodes or not all(isinstance(t, str) and t in nodes for t in targets):
            raise ValueError('annotation contains an unknown skill identity')
        uses[source] = sorted(set(targets))
    incoming = {identity: [] for identity in nodes}
    for source, targets in uses.items():
        for target in targets:
            if target not in incoming:
                raise ValueError('unresolved existing declaration: ' + target)
            incoming[target].append(source)
    changes = []
    for identity, node in nodes.items():
        if node.get('kind') == 'workflow' or node.get('read_only'):
            continue
        path = Path(node['path'])
        if digest(path.read_bytes()) != node['sha256']:
            raise ValueError(f'{identity}: concurrent change; regenerate proposal')
        data, body = frontmatter(path)
        meta = dict(data.get('metadata', {}))
        if not uses[identity] and not incoming[identity] and not any(k.startswith('skill-graph-') for k in meta):
            continue
        meta['skill-graph-id'] = identity
        meta['skill-graph-uses'] = ', '.join(uses[identity])
        meta['skill-graph-used-by'] = ', '.join(sorted(incoming[identity]))
        if 'uses' in data:
            data['uses'] = ['[['+target+'/SKILL]]' for target in uses[identity]]
        if 'used-by' in data:
            data['used-by'] = ['[['+target+'/SKILL]]' for target in sorted(incoming[identity])]
        if meta == data.get('metadata', {}):
            continue
        data['metadata'] = meta
        proposed = '---\n' + yaml.safe_dump(data, sort_keys=False, allow_unicode=True) + '---\n' + body
        target = output / identity / 'SKILL.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposed)
        target.chmod(path.stat().st_mode & 0o777)
        changes.append({'id': identity, 'active_path': str(path), 'staged_path': str(target.absolute()),
                        'before_sha256': node['sha256'], 'after_sha256': digest(proposed.encode())})
    output.mkdir(parents=True, exist_ok=True)
    (output / 'changes.json').write_text(json_text(changes) + '\n')
    return changes


def atomic_text(path, content):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_graph(graph, output, roots=None, expected_roots=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / '.skill-graph-lock'
    lock.mkdir()
    try:
        if expected_roots is not None and (output / 'roots.json').read_bytes() != expected_roots:
            raise ValueError('Registered roots changed concurrently')
        previous = output / 'graph.json'
        if previous.exists():
            old = read_json(previous)
            if old.get('concepts', {}).get('status') == 'fresh':
                identity = lambda value: sorted((n['id'], n['sha256']) for n in value['nodes'])
                if identity(old) == identity(graph):
                    graph['concepts'] = old['concepts']
                    graph['clusters'] = old.get('clusters', [])
                    mapped = {n['id']: n for n in old['nodes']}
                    for node in graph['nodes']:
                        for field in ('cluster', 'secondary_clusters', 'bridge_score'):
                            if field in mapped[node['id']]:
                                node[field] = mapped[node['id']][field]
                    known = {(e['source'], e['target'], e['relation']) for e in graph['edges']}
                    graph['edges'].extend(e for e in old['edges'] if (e['source'], e['target'], e['relation']) not in known)
                else:
                    graph['concepts'] = {'status': 'stale', 'reason': 'Inventory changed; run skill-search map.'}
        lines = ['# Skill graph', '', 'Generated from registered skills. Load selected entrypoints and useful neighbors only.', '',
                 f"{len(graph['nodes'])} canonical skills; {len(graph['aliases'])} aliases; {len(graph['edges'])} typed relationships.",
                 'Mapping status: ' + graph.get('concepts', {}).get('status', 'unavailable') + '.', '']
        for node in graph['nodes']:
            lines.append(f"- `{node['id']}` — {node['description'][:160]}")
        atomic_text(output / 'INDEX.md', '\n'.join(lines) + '\n')
        if roots is not None:
            atomic_text(output / 'roots.json', json_text(roots) + '\n')
        atomic_text(output / 'graph.json', json_text(graph) + '\n')
    finally:
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('build', 'audit', 'annotate'):
        p = sub.add_parser(name)
        p.add_argument('--roots', required=True)
        p.add_argument('--output', required=True)
        if name == 'annotate':
            p.add_argument('--declarations', help='Optional JSON map of scoped IDs to outgoing target lists; otherwise use frontmatter')
    for name in ('neighbors', 'check'):
        p = sub.add_parser(name)
        p.add_argument('--graph', required=True)
        if name == 'neighbors':
            p.add_argument('identity')
    args = parser.parse_args()
    try:
        if args.command in {'neighbors', 'check'}:
            graph = read_json(args.graph)
            errors = check(graph)
            if errors:
                raise ValueError('\n'.join(errors))
            if args.command == 'check':
                print(json_text({'status': 'passed', 'nodes': len(graph['nodes']), 'edges': len(graph['edges'])}))
            else:
                nodes = {n['id']: n for n in graph['nodes']}
                node = nodes.get(args.identity)
                if node is None:
                    alias = next((a for a in graph['aliases'] if a['id'] == args.identity), None)
                    if alias:
                        node = nodes[alias['target']]
                if node is None:
                    matches = [n for n in graph['nodes'] if n['name'] == args.identity]
                    if len(matches) != 1:
                        raise ValueError('Use an exact scoped ID; name is missing or ambiguous')
                    node = matches[0]
                print(json_text({'skill': {k: node[k] for k in ['id', 'name', 'path']},
                                  'uses': [{k: nodes[i][k] for k in ['id', 'name', 'path']} for i in node['uses']],
                                  'used_by': [{k: nodes[i][k] for k in ['id', 'name', 'path']} for i in node['used_by']]}))
            return 0
        graph = inventory(read_json(args.roots))
        if graph['errors']:
            raise ValueError('\n'.join(graph['errors']))
        if args.command == 'annotate':
            changes = annotate(graph, read_json(args.declarations) if args.declarations else {}, args.output)
            print(json_text({'staged_changes': len(changes)}))
        elif args.command == 'audit':
            groups = {}
            for node in graph['nodes']:
                groups.setdefault(fingerprint(Path(node['path']).parent), []).append(node)
            result = {'exact_duplicates': [[{'id': n['id'], 'path': n['path']} for n in group] for group in groups.values() if len(group) > 1], 'aliases': graph['aliases']}
            Path(args.output).write_text(json_text(result) + '\n')
            print(json_text({'duplicate_groups': len(result['exact_duplicates'])}))
        else:
            errors = check(graph, hashes=False)
            if errors:
                raise ValueError('\n'.join(errors))
            write_graph(graph, args.output)
            print(json_text({'nodes': len(graph['nodes']), 'aliases': len(graph['aliases']), 'edges': len(graph['edges'])}))
        return 0
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
