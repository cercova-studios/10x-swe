"""CLI journey and failure checks; pass the candidate skill-search binary."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main(binary):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        root = base / 'skills'
        skill = root / 'example' / 'SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: example\ndescription: local graph maintenance\n---\n')
        (base / 'roots.json').write_text(json.dumps({'roots': [{'id': 'global', 'path': str(root)}]}))

        def run(*args, success=True):
            result = subprocess.run(
                [binary, '--graph', str(base / 'graph.json'), '--state', str(base / 'state'), *args],
                capture_output=True, text=True, timeout=240,
            )
            assert (result.returncode == 0) == success, result.stdout + result.stderr
            return json.loads(result.stdout if success else result.stderr)

        run('refresh')
        skill.write_text(skill.read_text().replace('local graph maintenance', 'changed inventory discovery'))
        assert 'skill changed' in run('search', 'changed', success=False)['error']
        run('refresh')
        assert run('search', 'changed')['local']['results'][0]['id'] == 'global/example'
        assert run('clusters')['total_clusters'] >= 1
        before = (base / 'graph.json').read_bytes()
        skill.write_text('---\nname: example\ndescription: broken\nmetadata:\n  skill-graph-uses: global/missing\n---\n')
        assert 'inventory rebuild failed' in run('refresh', success=False)['error']
        assert (base / 'graph.json').read_bytes() == before
        assert not (base / '.skill-graph-lock').exists()
    print('refresh journey and failed-build preservation passed')


if __name__ == '__main__':
    main(sys.argv[1])
