#!/usr/bin/env python3
"""Static checks for every plugin component, run in CI and before release.

1. Skills follow the Agent Skills spec (https://agentskills.io/specification):
   strict YAML frontmatter, name == directory, lowercase-hyphen name <= 64,
   description 1-1024 characters, compatibility <= 500, string metadata, and
   names unique across all plugins (hosts merge skills into one namespace).
2. Agents and commands have strict-YAML frontmatter with a description; agent
   names are unique and descriptions <= 1024 characters.
3. Every bundled path a skill tells the agent to read or run
   (references/, workflows/, templates/, assets/, scripts/) exists.
4. Generated host adapters and catalogs match their canonical sources
   (delegates to scripts/hosts.py check).

Requires PyYAML.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import hosts  # noqa: E402

NAME = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
REFERENCE = re.compile(r'(?<![\w./{<-])((?:references|workflows|templates|assets|scripts)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)')
# Authoring guides that discuss hypothetical skill layouts rather than files
# the agent is told to open. Paths in them are examples by design.
EXAMPLE_ONLY = {'create-agent-skills'}


def strip_fences(text):
    return re.sub(r'^(```|~~~).*?^\1[^\n]*$', '', text, flags=re.M | re.S)


def check_skill(folder, errors, names):
    rel = folder.relative_to(ROOT)
    try:
        data, _ = hosts.parse_frontmatter(folder / 'SKILL.md')
    except Exception as error:  # noqa: BLE001 - report every parse failure
        errors.append(f'{rel}/SKILL.md: frontmatter does not parse: {error}')
        return
    name, description = data.get('name'), data.get('description')
    if not isinstance(name, str) or not NAME.match(name) or len(name) > 64:
        errors.append(f'{rel}: name {name!r} must be 1-64 lowercase letters, digits and single hyphens')
    elif name != folder.name:
        errors.append(f'{rel}: name {name!r} must match its directory {folder.name!r}')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        errors.append(f'{rel}: description must be a non-empty string of at most 1024 characters')
    compatibility = data.get('compatibility')
    if compatibility is not None and (not isinstance(compatibility, str) or not 0 < len(compatibility) <= 500):
        errors.append(f'{rel}: compatibility must be a string of 1-500 characters')
    metadata = data.get('metadata', {})
    if not isinstance(metadata, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
        errors.append(f'{rel}: metadata must map strings to strings')
    if isinstance(name, str):
        if name in names:
            errors.append(f'{rel}: skill name {name!r} duplicates {names[name]}')
        names[name] = rel


def check_references(folder, errors):
    if folder.name in EXAMPLE_ONLY:
        return
    documents = [folder / 'SKILL.md'] + sorted((folder / 'workflows').glob('*.md'))
    for document in documents:
        for number, line in enumerate(strip_fences(document.read_text(encoding='utf-8')).splitlines(), 1):
            for match in REFERENCE.finditer(line):
                ref = match.group(1).rstrip('.')
                if not ((folder / ref).exists() or (document.parent / ref).exists()):
                    errors.append(f'{document.relative_to(ROOT)}: references missing file {ref}')


def check_markdown_component(path, errors, names=None):
    rel = path.relative_to(ROOT)
    try:
        data, _ = hosts.parse_frontmatter(path)
    except Exception as error:  # noqa: BLE001
        errors.append(f'{rel}: frontmatter does not parse: {error}')
        return
    description = data.get('description')
    if not isinstance(description, str) or not description.strip():
        errors.append(f'{rel}: description must be a non-empty string')
    elif len(description) > 1024:
        errors.append(f'{rel}: description is {len(description)} characters; keep it under 1024 and move examples to the body')
    for key in ('argument-hint',):
        if key in data and not isinstance(data[key], str):
            errors.append(f'{rel}: {key} must be a quoted string (YAML parsed a {type(data[key]).__name__})')
    if names is not None:
        name = data.get('name', path.stem)
        if name in names:
            errors.append(f'{rel}: agent name {name!r} duplicates {names[name]}')
        names[name] = rel


def main():
    errors, skill_names = [], {}
    _, items = hosts.plugins()
    counts = []
    for item in items:
        skills, agents, commands = hosts.components(item['root'])
        agent_names = {}
        for folder in skills:
            check_skill(folder, errors, skill_names)
            check_references(folder, errors)
        for path in agents:
            check_markdown_component(path, errors, agent_names)
        for path in commands:
            check_markdown_component(path, errors)
        counts.append(f"{item['entry']['name']}: {len(skills)} skills, {len(agents)} agents, {len(commands)} commands")
    for error in errors:
        print('ERROR:', error, file=sys.stderr)
    status = subprocess.run([sys.executable, str(ROOT / 'scripts/hosts.py'), 'check']).returncode
    if errors or status:
        return 1
    print('OK: ' + '; '.join(counts))
    return 0


if __name__ == '__main__':
    sys.exit(main())
