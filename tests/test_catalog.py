"""Public catalog contracts, provenance, cache integrity and failure boundaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1]/'plugins/10x-swe/skills/web-research/scripts/catalog.py'
spec = importlib.util.spec_from_file_location('catalog', SCRIPT)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)/'work'
        self.request = {'schema': 'research-request/v1', 'topics': [{'name': 'Agents', 'query': 'coding agent evaluation'}]}

    def fetch(self, responses):
        def get(url, work):
            value = responses[url]
            raw = (json.dumps(value) if not isinstance(value, str) else value).encode()
            return raw, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'retrieved_at': '2026-10-18T12:00:00+00:00'}
        return patch.object(c, 'download', side_effect=get)

    def test_zenml_index_times_and_year_are_not_publication_dates(self):
        row = {'title': 'Coding agent evaluation', 'summary': 'A vendor describes agent evaluation.',
               'slug': 'case', 'link': 'https://example.org/original', 'addedAt': 1792000000000, 'year': 2026}
        with self.fetch({'https://www.zenml.io/llmops-index.json': [row, dict(row, link='file:///private/data')]}):
            records = c.acquire('zenml', self.request, self.work)
        source = records[0]
        self.assertIsNone(source['published_at'])
        self.assertEqual(source['original_url'], row['link'])
        self.assertEqual(source['url'], 'https://www.zenml.io/llmops-database/case')
        self.assertEqual(source['evidence_kind'], 'secondary-summary')
        self.assertEqual(source['provenance'][0]['catalog_added_at'], row['addedAt'])
        self.assertEqual(records[-1]['selected'], 1)

    def test_aietalks_retains_native_evidence_and_recording_date(self):
        page = '# Coding agent evaluation\nSource: https://www.youtube.com/watch?v=abcdefghijk\nPublished: 2025-12-02\n\nAn edited summary of an evaluation workflow.'
        with self.fetch({'https://aietalks.com/llms.txt': '- [Coding agent evaluation](https://aietalks.com/talks/example): A coding agent evaluation.\n',
                         'https://aietalks.com/talks/example.md': page}):
            source = c.acquire('aietalks', self.request, self.work)[0]
        self.assertEqual(source['published_at'], '2025-12-02')
        self.assertEqual(source['provenance'][0]['video_id'], 'abcdefghijk')
        self.assertIn('not a transcript', source['coverage'])
        self.assertEqual(source['content'], page)

    def official(self, segments):
        return {'https://ai.engineer/api/data/talks?format=json': [
                    {'title': 'Coding agent evaluation', 'summary': 'Coding agent evaluation.', 'slug': 'example',
                     'videoId': 'abcdefghijk', 'url': 'https://ai.engineer/talks/example'}],
                'https://ai.engineer/api/data/transcripts?format=json': [
                    {'talkSlug': 'example', 'jsonUrl': 'https://ai.engineer/api/data/transcript?slug=example&format=json'}],
                'https://ai.engineer/api/data/transcript?slug=example&format=json': segments}

    def test_official_transcript_preserves_milliseconds_and_passage_bounds(self):
        segments = [{'startMs': 21030, 'text': 'An official automated passage about coding agent evaluation.'},
                    {'startMs': 52000, 'text': 'x'*6000}]
        with self.fetch(self.official(segments)):
            source = c.acquire('ai-engineer', self.request, self.work)[0]
        passage = source['provenance'][0]['segments'][0]
        self.assertEqual(passage['startMs'], 21030)
        self.assertEqual(passage['citation_url'], 'https://www.youtube.com/watch?v=abcdefghijk&t=21')
        self.assertEqual(source['content'], segments[0]['text'])
        self.assertIsNone(source['published_at'])
        self.assertEqual(source['evidence_kind'], 'primary-transcript')

    def test_malformed_transcript_and_changed_requests_fail(self):
        with self.fetch(self.official([{'startMs': -1, 'text': 'An invalid passage.'}])):
            with self.assertRaisesRegex(ValueError, 'transcript schema'):
                c.acquire('ai-engineer', self.request, self.work)
        with patch.object(c, 'download') as fetch:
            with self.assertRaisesRegex(ValueError, 'request changed'):
                c.acquire('ai-engineer', self.request, self.work, limit=1)
            fetch.assert_not_called()

    def test_cache_hash_failure_and_unsafe_destinations_never_fetch(self):
        self.work.mkdir()
        url = 'https://aietalks.com/llms.txt'
        key = hashlib.sha256(url.encode()).hexdigest()
        (self.work/(key+'.body')).write_text('tampered')
        (self.work/(key+'.json')).write_text(json.dumps({'url': url, 'sha256': 'wrong'}))
        with patch.object(c, 'build_opener') as network:
            with self.assertRaisesRegex(ValueError, 'changed'):
                c.download(url, self.work)
            for url in ['https://localhost/private', 'file:///private/data', 'https://user:pass@ai.engineer/data']:
                with self.assertRaises(ValueError):
                    c.download(url, self.work)
            network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
