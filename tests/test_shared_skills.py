"""Portable authoring helpers and shared bundle safety contracts."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT/'plugins/10x-swe/skills'
AUTHOR = SKILLS/'create-agent-skills'
spec = importlib.util.spec_from_file_location('author_validator', AUTHOR/'scripts/quick_validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class SharedSkills(unittest.TestCase):
    def test_initializer_validation_and_overwrite_denial(self):
        with tempfile.TemporaryDirectory(prefix='skill-authoring-') as directory:
            argv = [sys.executable,str(AUTHOR/'scripts/init_skill.py'),'public-fixture',
                    '--path',directory,'--resources','scripts,references']
            result = subprocess.run(argv,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            folder = Path(directory)/'public-fixture'
            self.assertTrue((folder/'scripts').is_dir())
            self.assertTrue((folder/'references').is_dir())
            text = '---\nname: public-fixture\ndescription: Inspects a public fixture.\nmetadata:\n  skill-graph-id: existing/fixture/public-fixture\n---\nRead fixture data only.\n'
            (folder/'SKILL.md').write_text(text)
            self.assertEqual(validator.validate_skill(folder),(True,'Skill is valid!'))
            result = subprocess.run(argv,capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((folder/'SKILL.md').read_text(),text)

    def test_metadata_boundaries(self):
        valid = {'name':'public-fixture','description':'Inspects a public fixture.'}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for change in [{'name':''},{'description':''},{'metadata':{'count':4}},
                           {'metadata':[]},{'name':'../escape'}]:
                with self.subTest(change=change):
                    (folder/'SKILL.md').write_text('---\n'+yaml.safe_dump(valid|change)+'---\nFixture.\n')
                    self.assertFalse(validator.validate_skill(folder)[0])

    def test_isolated_ghidra_and_turnstile_contracts_are_shipped(self):
        # Contract checks supplement the runnable helper suites; they do not prove agent adherence.
        self.assertTrue((SKILLS/'ghidra/scripts/ghidra_scripts/ExportSummary.java').is_file())
        self.assertFalse((SKILLS/'ghidra/references/legacy-exports.md').exists())
        self.assertFalse((SKILLS/'chrome-devtools/scripts/bun.lock').exists())
        self.assertFalse((SKILLS/'playwright/scripts/playwright_cli.sh').exists())
        self.assertTrue((SKILLS/'frontend-design/LICENSE.txt').is_file())
        self.assertTrue((AUTHOR/'references/skill-creator-LICENSE.txt').is_file())
        wizard = (SKILLS/'turnstile-spin/references/creation-wizard.md').read_text()
        self.assertIn('quarantine-bundle',wizard)
        self.assertIn('cleanup_failed',wizard)


if __name__=='__main__':
    unittest.main()
