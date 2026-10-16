"""Behavioral checks using temporary skill fixtures; no active skill changes."""
import tempfile
import unittest
from pathlib import Path

import graph


class GraphTests(unittest.TestCase):
    def test_workflows_are_inert_typed_nodes_with_owned_hashes_and_aliases(self):
        owner = self.skill('owner')
        participant = self.skill('participant')
        participant.write_text(participant.read_text().replace('metadata:\n', 'metadata:\n  skill-graph-workflows: global/owner/workflows/example\n'))
        folder = owner.parent / 'workflows'; folder.mkdir()
        runner = folder / 'example.yaml'; runner.write_text('run: touch SHOULD_NEVER_RUN\n')
        doc = folder / 'example.md'
        doc.write_text('---\nschema: workflow/v1\nname: example\ndescription: session learning\nskills: [global/participant]\nrunner: workflows/example.yaml\nresources: [workflows/example.yaml]\n---\nReview before execution.\n')
        (self.root/'alias').symlink_to(owner.parent, target_is_directory=True)
        result = graph.inventory(self.config)
        self.assertEqual(result['errors'], [])
        workflow = next(n for n in result['nodes'] if n.get('kind') == 'workflow')
        self.assertEqual(workflow['uses'], [])
        self.assertEqual({e['relation'] for e in result['edges']}, {'associated_workflow', 'uses_skill'})
        self.assertEqual(graph.check(result), [])
        self.assertTrue(any(a['target'] == workflow['id'] for a in result['aliases']))
        graph.annotate(result, {}, self.base/'proposal')
        self.assertFalse((self.base/'proposal'/workflow['id']/'SKILL.md').exists())
        runner.write_text('changed\n')
        self.assertTrue(any('resource changed' in e for e in graph.check(result)))
        runner.unlink(); runner.symlink_to(participant)
        self.assertTrue(graph.inventory(self.config)['errors'])
        self.assertFalse((self.base/'SHOULD_NEVER_RUN').exists())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'skills'
        self.root.mkdir()
        self.config = {'roots': [{'id': 'global', 'path': str(self.root)}]}

    def tearDown(self):
        self.temp.cleanup()

    def skill(self, folder, uses='', name=None):
        path = self.root / folder / 'SKILL.md'
        path.parent.mkdir(parents=True)
        path.write_text(f'---\nname: {name or folder}\ndescription: café\nmetadata:\n  skill-graph-uses: "{uses}"\n---\n\nBody stays exact.\n')
        return path

    def test_reciprocal_proposal_preserves_body_and_active_file(self):
        a = self.skill('a', 'global/b')
        self.skill('b')
        before = a.read_bytes()
        changes = graph.annotate(graph.inventory(self.config), {}, self.base / 'proposal')
        self.assertEqual(len(changes), 2)
        self.assertEqual(a.read_bytes(), before)
        for change in changes:
            proposed = Path(change['staged_path'])
            self.assertEqual(graph.frontmatter(proposed)[1], '\nBody stays exact.\n')
        b_data, _ = graph.frontmatter(self.base / 'proposal/global/b/SKILL.md')
        self.assertEqual(b_data['metadata']['skill-graph-used-by'], 'global/a')

    def test_aliases_and_same_name_variants(self):
        a = self.skill('a', name='shared')
        self.skill('b', name='shared')
        (self.root / 'alias').symlink_to(a.parent, target_is_directory=True)
        result = graph.inventory(self.config)
        self.assertEqual(len(result['nodes']), 2)
        self.assertEqual(len(result['aliases']), 1)
        self.assertEqual(len({n['id'] for n in result['nodes']}), 2)

    def test_early_alias_does_not_rename_canonical(self):
        a = self.skill('z-real')
        (self.root / 'a-alias').symlink_to(a.parent, target_is_directory=True)
        self.skill('consumer', 'global/z-real')
        result = graph.inventory(self.config)
        self.assertEqual(result['errors'], [])
        self.assertIn('global/z-real', {n['id'] for n in result['nodes']})

    def test_crlf_body_preserved(self):
        a = self.skill('a', 'global/b')
        self.skill('b')
        a.write_bytes(a.read_bytes().replace(b'\n', b'\r\n'))
        graph.annotate(graph.inventory(self.config), {}, self.base / 'proposal')
        self.assertTrue((self.base / 'proposal/global/a/SKILL.md').read_bytes().endswith(b'\r\nBody stays exact.\r\n'))

    def test_unresolved_and_invalid_identity(self):
        self.skill('a', 'global/missing')
        self.assertIn('unresolved', graph.inventory(self.config)['errors'][0])
        self.assertFalse(graph.valid_identity('../outside'))
        self.assertFalse(graph.valid_identity('/absolute'))

    def test_stale_backlinks_and_new_skill_detected(self):
        self.skill('a')
        result = graph.inventory(self.config)
        self.assertEqual(graph.check(result), [])
        self.skill('b')
        self.assertTrue(any('inventory' in e for e in graph.check(result)))
        (self.root / 'a/SKILL.md').write_text('---\nname: a\nmetadata:\n  skill-graph-used-by: global/b\n---\n')
        self.assertTrue(any('backlinks' in e for e in graph.check(graph.inventory(self.config))))

    def test_broken_alias_and_missing_root_fail(self):
        (self.root / 'broken').symlink_to('missing')
        self.assertTrue(graph.inventory(self.config)['errors'])
        self.assertTrue(graph.inventory({'roots': [{'id': 'global', 'path': str(self.base / 'missing')} ]})['errors'])

    def test_cycle_fail(self):
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'loop').symlink_to(self.root, target_is_directory=True)
        self.assertTrue(graph.inventory(self.config)['errors'])

    def test_full_bundle_fingerprint_and_json(self):
        a, b = self.skill('a', name='same'), self.skill('b', name='same')
        self.assertEqual(graph.fingerprint(a.parent), graph.fingerprint(b.parent))
        (b.parent / 'helper.txt').write_text('different')
        self.assertNotEqual(graph.fingerprint(a.parent), graph.fingerprint(b.parent))
        value = {'unicode': 'café', 'uses': ['global/a']}
        path = self.base / 'graph.json'
        graph.atomic_text(path, graph.json_text(value))
        self.assertEqual(graph.read_json(path), value)

    def test_bad_declarations_and_existing_output_fail(self):
        self.skill('a')
        result = graph.inventory(self.config)
        with self.assertRaises(ValueError):
            graph.annotate(result, {'global/a': ['global/missing']}, self.base / 'proposal')
        with self.assertRaises(ValueError):
            graph.annotate(result, {}, self.base)

    def test_graph_writer_respects_promotion_lock(self):
        self.skill('a')
        output = self.base / 'index'
        output.mkdir()
        (output / '.skill-graph-lock').mkdir()
        with self.assertRaises(FileExistsError):
            graph.write_graph(graph.inventory(self.config), output)
        self.assertFalse((output / 'graph.json').exists())


if __name__ == '__main__':
    unittest.main()
