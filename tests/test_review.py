"""Read-only review must reject invalid citations before issuing an approval digest."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/knowledge/skills/source-insights/scripts'


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.library = self.root / 'never-publish'
        self.sid = 'session:codex:review-fixture'
        quote = 'A recorded fixture claim, not independently verified.'
        version = 'a' * 64
        tid = 'turn:codex:review-fixture:3'
        details = dict(agent='codex', session_id='review-fixture', source_path='/unavailable/session.jsonl',
                       jsonl_line=3, json_pointer='$.payload.content', role='assistant', timestamp=None,
                       record_sha256=version, original_text_sha256=version, indexed_text_sha256='b'*64,
                       excerpt_sha256=hashlib.sha256(quote.encode()).hexdigest(), char_start=0,
                       char_end=len(quote), redacted=False, quote=quote, version=version, session_revision=version)
        packet = dict(schema='knowledge-snapshot/v1', corpus='sessions', nodes=[
            dict(id=self.sid, kind='session', label='Fixture', details=dict(version=version, coverage={})),
            dict(id=tid, kind='session_turn', details=details)],
            edges=[dict(a=tid, b=self.sid, kind='part_of', status='recorded')],
            versions={self.sid: version, tid: version}, hits=[])
        self.records = self.root / 'selected.jsonl'
        self.records.write_text(json.dumps(packet))
        self.assertEqual(self.recipe('capture', '--records', str(self.records)).returncode, 0)
        self.assertEqual(self.recipe('prepare').returncode, 0)
        lines = (self.work/'evidence/document.md').read_text().splitlines()
        line = lines.index(quote)+1
        self.analysis = dict(title='Review fixture', summary='Citation checking only.', tags=['fixture'],
            coverage=dict(line_ranges=[[1, len(lines)]], limitations=['Selected fixture excerpt only.']),
            insights=[dict(claim=quote, status='source-claim', why_it_matters='Tests a review boundary.',
                application='Inspect citations before approval.', caveats='Synthetic, unverified evidence.',
                evidence=[dict(line_start=line, line_end=line, quote=quote)])])
        self.save(self.analysis)

    def run_script(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS/script), *map(str, args)],
            env=dict(os.environ, PATH='/no-companion-tools', AGENT_KNOWLEDGE_HOME=str(self.root/'absent-install')),
            capture_output=True, timeout=30)

    def recipe(self, operation, *args):
        return self.run_script('session_workflow.py', operation, '--work', self.work,
            '--session', self.sid, '--library', self.library, *args)

    def save(self, analysis):
        (self.work/'analysis.json').write_text(json.dumps(analysis))

    def assert_denied(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(result.stdout)
        self.assertNotIn(b'Traceback', result.stderr)
        self.assertNotIn(b'ERROR: ERROR:', result.stderr)
        self.assertFalse(self.library.exists())
        self.assertFalse((self.work/'publication.json').exists())

    def test_invalid_quote_and_changed_evidence_cannot_get_review_digest(self):
        bad = copy.deepcopy(self.analysis)
        bad['insights'][0]['evidence'][0]['quote'] = 'This quote is absent.'
        self.save(bad)
        self.assert_denied(self.recipe('review'))
        self.save(self.analysis)
        with (self.work/'evidence/source.md').open('a') as stream:
            stream.write('changed')
        self.assert_denied(self.recipe('review'))

    def test_valid_review_and_standalone_validation_do_not_publish_or_mutate_evidence(self):
        before = {str(p.relative_to(self.work)): p.read_bytes() for p in self.work.rglob('*') if p.is_file()}
        result = self.run_script('sources.py', 'validate', self.work/'evidence', self.work/'analysis.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'valid')
        result = self.recipe('review')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['validation']['status'], 'valid')
        self.assertEqual(before, {str(p.relative_to(self.work)): p.read_bytes() for p in self.work.rglob('*') if p.is_file()})
        self.assertFalse(self.library.exists())
        self.assertFalse((self.work/'publication.json').exists())

    def test_malformed_analysis_is_a_clean_validation_error(self):
        for analysis in ({}, [], dict(self.analysis, coverage=[])):
            self.save(analysis)
            self.assert_denied(self.run_script('sources.py', 'validate', self.work/'evidence', self.work/'analysis.json'))


if __name__ == '__main__':
    unittest.main()
