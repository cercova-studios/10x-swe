"""Validate discoverable plugin metadata and keep the linked catalog complete."""
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ENGINEERING = ROOT / 'plugins/10x-swe'


def frontmatter(path):
    lines = path.read_text().splitlines()
    if not lines or lines[0] != '---':
        raise ValueError(f'{path}: missing frontmatter')
    end = lines.index('---', 1)
    metadata = yaml.safe_load('\n'.join(lines[1:end]))
    if not isinstance(metadata, dict):
        raise ValueError(f'{path}: frontmatter must be a mapping')
    return metadata


class PluginMetadataTests(unittest.TestCase):
    def test_skill_agent_and_command_frontmatter(self):
        for plugin in sorted((ROOT / 'plugins').iterdir()):
            for kind, pattern in [('skills', '*/SKILL.md'), ('agents', '*.md'), ('commands', '*.md')]:
                names = {}
                for path in sorted((plugin / kind).glob(pattern)):
                    with self.subTest(path=path.relative_to(ROOT)):
                        metadata = frontmatter(path)
                        required = ('description',) if kind == 'commands' else ('name', 'description')
                        for field in required:
                            self.assertIsInstance(metadata.get(field), str)
                            self.assertTrue(metadata[field].strip(), field)
                        name = metadata.get('name', path.stem)
                        self.assertNotIn(name, names, f'{name}: {names.get(name)} and {path}')
                        names[name] = path
                        if kind == 'agents':
                            self.assertIn(metadata.get('model', 'inherit'), ('inherit', 'sonnet', 'opus', 'haiku'))

    def test_engineering_catalog_links_every_entrypoint(self):
        catalog = (ENGINEERING / 'README.md').read_text()
        links = re.findall(r'\]\(([^)]+)\)', catalog)
        for kind, pattern in [('skills', '*/SKILL.md'), ('agents', '*.md'), ('commands', '*.md')]:
            expected = {p.relative_to(ENGINEERING).as_posix() for p in (ENGINEERING / kind).glob(pattern)}
            actual = {link for link in links if link.startswith(kind + '/')}
            self.assertEqual(actual, expected, f'{kind} catalog drift')
            for link in actual:
                self.assertTrue((ENGINEERING / link).is_file(), link)

    def test_portable_examples_use_installed_commands(self):
        for path in [ROOT / 'plugins/knowledge/tools/bkd/README.md',
                     ROOT / 'plugins/knowledge/skills/skill-graph/references/remote-loading.md',
                     ROOT / 'plugins/knowledge/skills/source-insights/references/search.md']:
            text = path.read_text()
            self.assertNotIn('python3 ~/.agents/skills/source-insights/scripts/sources.py', text)
            self.assertNotIn('~/.agents/bin/skill-search', text)


if __name__ == '__main__':
    unittest.main()
