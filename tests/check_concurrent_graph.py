"""A stale intake proposal cannot overwrite newly registered roots."""
import importlib.util
from pathlib import Path
import tempfile

path=Path(__file__).resolve().parents[1]/'plugins/knowledge/skills/skill-graph/scripts/graph.py'
spec=importlib.util.spec_from_file_location('graph',path)
graph=importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'roots.json').write_bytes(b'newer roots')
    try:
        graph.write_graph({'nodes':[],'aliases':[],'edges':[]},root,roots={'roots':[]},expected_roots=b'old roots')
    except ValueError as error:
        assert 'concurrently' in str(error)
    else: raise AssertionError('stale roots overwrote new state')
    assert (root/'roots.json').read_bytes()==b'newer roots'
    assert not (root/'graph.json').exists() and not (root/'.skill-graph-lock').exists()
print('PASS: stale intake cannot overwrite concurrent roots; lock released')
