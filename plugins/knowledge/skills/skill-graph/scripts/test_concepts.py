"""Portable notes and mapping lifecycle, using isolated skill fixtures."""
import tempfile
import unittest
from pathlib import Path
import graph
import concepts

class ConceptsTests(unittest.TestCase):
    def test_workflow_vault_keeps_typed_links_without_copying_runner(self):
        owner=self.root/'a'
        (owner/'workflows').mkdir()
        (owner/'workflows/learn.yaml').write_text('run: never execute\n')
        doc=owner/'workflows/learn.md'
        doc.write_text('---\nschema: workflow/v1\nname: learn\nskills: [global/b]\nrunner: workflows/learn.yaml\nresources: [workflows/learn.yaml]\n---\nInspect before running.\n')
        entry=owner/'SKILL.md';entry.write_text(entry.read_text().replace('metadata:\n','metadata:\n  skill-graph-workflows: global/a/workflows/learn\n'))
        value=graph.inventory(self.config);self.assertEqual(value['errors'],[])
        before=doc.read_bytes();output=self.base/'vault'
        concepts.export_vault(value,output)
        self.assertTrue((output/'global/a/workflows/learn/WORKFLOW.md').is_file())
        self.assertFalse(list(output.rglob('*.yaml')))
        self.assertIn('[[global/a/workflows/learn/WORKFLOW]]',(output/'global/a/SKILL.md').read_text())
        self.assertIn('[[global/b/SKILL]]',(output/'global/a/workflows/learn/WORKFLOW.md').read_text())
        self.assertEqual(doc.read_bytes(),before)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'skills';self.root.mkdir()
        for name,uses in [('a','global/b'),('b','')]:
            folder=self.root/name;folder.mkdir()
            (folder/'SKILL.md').write_text(f'---\nname: {name}\ndescription: fixture {name}\nmetadata:\n  skill-graph-uses: "{uses}"\n  skill-graph-used-by: "'+('global/a' if name=='b' else '')+'"\n---\n\nOriginal instructions.\n')
        self.config={'roots':[{'id':'global','path':str(self.root)}]}
        self.value=graph.inventory(self.config)
    def tearDown(self):self.temp.cleanup()
    def test_export_roundtrip_declared_uses_and_body_links(self):
        before=[Path(n['path']).read_bytes() for n in self.value['nodes']]
        output=self.base/'vault';concepts.export_vault(self.value,output)
        result=graph.inventory({'roots':[{'id':'global','path':str(output/'global')}]})
        self.assertEqual(result['errors'],[])
        self.assertEqual(graph.check(result),[])
        self.assertEqual([e for e in result['edges'] if e['relation']=='uses'],self.value['edges'])
        data,body=graph.frontmatter(output/'global/a/SKILL.md')
        self.assertEqual(data['uses'],['[[global/b/SKILL]]'])
        self.assertIn('[[global/b/SKILL]]',body)
        self.assertIn('Original instructions.',body)
        self.assertEqual(before,[Path(n['path']).read_bytes() for n in self.value['nodes']])
        with self.assertRaises(FileExistsError):concepts.export_vault(self.value,output)
    def test_portable_missing_body_link_is_rejected(self):
        path=self.root/'a/SKILL.md'
        path.write_text('---\nname: a\nuses: ["[[global/b/SKILL]]"]\n---\nMissing link.\n')
        self.assertTrue(any('matching direct body link' in error for error in graph.inventory(self.config)['errors']))
    def test_existing_plain_reference_topics_are_preserved(self):
        path=self.root/'a/SKILL.md';path.write_text(path.read_text().replace('description: fixture a','description: fixture a\nreferences: [workers, pages]'))
        value=graph.inventory(self.config);self.assertEqual(value['errors'],[])
        output=self.base/'vault';concepts.export_vault(value,output)
        data,_=graph.frontmatter(output/'global/a/SKILL.md')
        self.assertEqual(data['references'],['workers','pages'])
        self.assertEqual(graph.inventory({'roots':[{'id':'global','path':str(output/'global')} ]})['errors'],[])
    def test_rebuild_preserves_fresh_mapping_then_marks_changes_stale(self):
        output=self.base/'index'
        mapped=dict(self.value,concepts={'status':'fresh','records':[]},clusters=[{'id':'fixture'}])
        graph.write_graph(mapped,output)
        graph.write_graph(graph.inventory(self.config),output)
        self.assertEqual(graph.read_json(output/'graph.json')['concepts']['status'],'fresh')
        path=self.root/'a/SKILL.md';path.write_text(path.read_text()+'\nChanged.\n')
        graph.write_graph(graph.inventory(self.config),output)
        self.assertEqual(graph.read_json(output/'graph.json')['concepts']['status'],'stale')
    def test_export_failure_leaves_no_partial_vault(self):
        self.value['nodes'][0]['path']=str(self.base/'missing/SKILL.md')
        output=self.base/'vault'
        with self.assertRaises((OSError,ValueError)):concepts.export_vault(self.value,output)
        self.assertFalse(output.exists())

if __name__=='__main__':unittest.main()
