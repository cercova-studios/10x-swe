import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
intake = load('intake', PACKAGE / 'intake.py')
graph = load('graph', PACKAGE / 'skills/skill-graph/scripts/graph.py')


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def skill(self, name, content='body', original=None, uses=''):
        path = self.root/name/'SKILL.md'; path.parent.mkdir(parents=True)
        path.write_text('---\nname: shared\ndescription: fixture\nmetadata:\n  skill-graph-id: '
                        +(original or 'global/'+name)+'\n  skill-graph-uses: "'+uses+'"\n---\n'+content)
        return path
    def test_full_bundle_duplicates_conflicts_and_no_execution(self):
        a=self.skill('a'); b=self.skill('b'); b.write_bytes(a.read_bytes())
        script=a.parent/'hook.sh'; script.write_text('touch MUST_NOT_RUN')
        (b.parent/'hook.sh').write_bytes(script.read_bytes())
        self.skill('different', 'different body')
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        report=intake.inspect([('test',self.root)])
        self.assertEqual(report['coverage'],'complete')
        self.assertEqual(len([r for r in report['skills'] if r['duplicate_of']]),1)
        self.assertIn('shared',report['name_conflicts'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.root/'MUST_NOT_RUN').exists())
    def test_partial_hidden_alias_malformed_and_cycles(self):
        a=self.skill('a'); (a.parent/'.hidden').mkdir()
        (a.parent/'.hidden/resource').write_text('not silently fingerprinted')
        (self.root/'bad').mkdir();(self.root/'bad/SKILL.md').write_text('invalid')
        report=intake.inspect([('test',self.root)])
        self.assertEqual(report['coverage'],'partial');self.assertTrue(report['issues'])
        self.assertIsNone(report['skills'][0]['duplicate_of'])
        (self.root/'loop').mkdir();(self.root/'loop/again').symlink_to(self.root)
        self.assertTrue(intake.inspect([('test',self.root)])['issues'])
    def test_untrusted_yaml_aliases_rejected(self):
        path=self.skill('a');path.write_text('---\nname: &x skill\ndescription: *x\n---\n')
        self.assertTrue(intake.inspect([('test',self.root)])['issues'])
    def test_namespaces_preserve_source_and_unresolved_edges(self):
        a=self.skill('a',original='global/a',uses='global/b, global/missing')
        b=self.skill('b',original='global/b')
        before={p:p.read_bytes() for p in (a,b)}
        config={'roots':[{'id':'existing/test/'+p.parent.name,'namespace':'existing/test',
                          'path':str(p.parent),'read_only':True} for p in (a,b)]}
        result=graph.inventory(config)
        self.assertEqual(graph.check(result),[])
        node=next(n for n in result['nodes'] if n['id']=='existing/test/a')
        self.assertEqual(node['uses'],['existing/test/b'])
        self.assertEqual(node['unresolved_references'],['global/missing'])
        self.assertEqual(node['trust'],'existing-unreviewed')
        graph.annotate(result,{},self.root/'proposal')
        self.assertFalse(list((self.root/'proposal').rglob('SKILL.md')))
        self.assertEqual(before,{p:p.read_bytes() for p in (a,b)})
        b.write_text(b.read_text()+'changed')
        self.assertTrue(graph.check(result))


if __name__ == '__main__': unittest.main()
