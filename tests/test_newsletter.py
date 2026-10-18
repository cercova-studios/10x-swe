"""Independent publication, failure recovery, citation and deletion boundaries."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]/'plugins/knowledge/skills/newsletter'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SKILL/'scripts'/f'{name}.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


n, research, draft, host = map(module, ['newsletter', 'research', 'draft', 'host'])


def fixture(work):
    quote = 'An exact source passage with enough context to support a concrete technical explanation.'
    r = {'schema': 'newsletter-research/v1', 'window_start': '2026-10-15T08:00:00+00:00',
         'window_end': '2026-10-18T08:00:00+00:00', 'topics': ['Research', 'Agents', 'Retrieval'],
         'limits': {'original_pages': 1}, 'sources': [{'id': 'source', 'url': 'https://example.org/article',
         'title': 'Original source', 'published_at': None, 'content': quote, 'coverage': 'excerpt'}]}
    stories = []
    for i in range(6):
        stories.append({'id': f'story-{i}', 'headline': f'Story {i}', 'topic': r['topics'][i % 3],
                        'kind': 'deep_dive' if i < 2 else 'brief', 'summary': 'A concrete mechanism.',
                        'technical_detail': 'Mechanism and constraint. ' * 70, 'why_it_matters': 'A testable tradeoff.',
                        'relevance': 'A proposed application.', 'limitations': 'Synthetic fixture only.',
                        'event_date': '', 'citations': [{'source_id': 'source', 'quote': quote}]})
    issue = {'title': '</script><script>window.injected=true</script>', 'standfirst': 'A fixture issue.',
             'editorial': 'Only synthetic evidence.', 'stories': stories}
    review = {'schema': 'newsletter-review/v1', 'approved': True, 'problems': [], 'assessment': 'Fixture only.',
              'issue_sha256': n.checksum(json.dumps(issue, ensure_ascii=False, sort_keys=True).encode()),
              'research_sha256': n.checksum(json.dumps(r, ensure_ascii=False, sort_keys=True).encode())}
    work.mkdir()
    for name, value in [('issue.json', issue), ('research.json', r), ('editorial-review.json', review)]:
        (work/name).write_text(json.dumps(value))
    return issue, r, review


class NewsletterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.work, self.root = self.base/'work', self.base/'store'
        self.issue, self.research, self.review = fixture(self.work)

    def test_publish_is_idempotent_and_html_injection_is_data(self):
        first = n.publish(self.root, self.work)
        before = {p.name: p.read_bytes() for p in first.iterdir()}
        self.assertEqual(first, n.publish(self.root, self.work))
        self.assertEqual(before, {p.name: p.read_bytes() for p in first.iterdir()})
        self.assertIn(b'\\u003c/script\\u003e', (self.root/'index.html').read_bytes())
        self.assertNotIn(b'<script>window.injected=true', (first/'issue.html').read_bytes())
        self.assertIn('A concrete mechanism.', (first/'issue.md').read_text())

    def test_changed_quotes_unreviewed_claims_and_stale_approval_fail(self):
        for mutate in [lambda i: i['stories'][0]['citations'][0].update(quote='Invented evidence '*4),
                       lambda i: i['stories'][0].update(headline='A changed claim'),
                       lambda i: i['stories'][0].update(citations=[])]:
            issue = copy.deepcopy(self.issue)
            mutate(issue)
            with self.assertRaises(ValueError):
                n.validate(issue, self.research, self.review)
        review = dict(self.review, approved=False)
        with self.assertRaises(ValueError):
            n.validate(self.issue, self.research, review)

    def test_refresh_failure_recovers_without_republishing(self):
        with patch.object(n, 'refresh', side_effect=OSError('simulated interrupted pointer update')):
            with self.assertRaises(OSError):
                n.publish(self.root, self.work)
        paths = list((self.root/'issues').glob('2026*'))
        self.assertEqual(len(paths), 1)
        manifest = (paths[0]/'manifest.json').read_bytes()
        n.publish(self.root, self.work)
        self.assertEqual(manifest, (paths[0]/'manifest.json').read_bytes())
        self.assertTrue((self.root/'index.html').is_file())

    def test_seven_days_uses_publication_time_and_has_dry_run(self):
        at = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
        old = n.publish(self.root, self.work, '2026-10-09', (at-timedelta(days=8)).isoformat())
        boundary = n.publish(self.root, self.work, '2026-10-11', (at-timedelta(days=7)).isoformat())
        os.utime(old, None)
        self.assertEqual(n.cleanup(self.root, at=at)['editions'], ['2026-10-09'])
        self.assertTrue(old.exists())
        unmanaged = self.root/'personal-notes.md'
        unmanaged.write_text('Must survive')
        n.cleanup(self.root, True, at)
        self.assertFalse(old.exists())
        self.assertTrue(boundary.exists())
        self.assertEqual(unmanaged.read_text(), 'Must survive')

    def test_tampered_and_symlink_entries_block_deletion_before_mutation(self):
        at = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
        old = n.publish(self.root, self.work, '2026-10-09', (at-timedelta(days=8)).isoformat())
        (self.root/'issues/2026-10-10').symlink_to(self.work, target_is_directory=True)
        with self.assertRaises(ValueError):
            n.cleanup(self.root, True, at)
        self.assertTrue(old.exists())
        self.assertTrue((self.work/'issue.json').exists())
        (self.root/'issues/2026-10-10').unlink()
        (old/'issue.md').write_text('tampered')
        with self.assertRaises(ValueError):
            n.cleanup(self.root, True, at)

    def test_interrupted_retention_replays_journal_and_keeps_unrelated_data(self):
        at = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
        n.publish(self.root, self.work, '2026-10-09', (at-timedelta(days=8)).isoformat())
        notes = self.root/'unrelated'
        notes.mkdir()
        (notes/'keep').write_text('safe')
        original = n.shutil.rmtree
        def fail(path):
            (path/'issue.json').unlink()
            raise OSError('interrupted cleanup')
        with patch.object(n.shutil, 'rmtree', side_effect=fail):
            with self.assertRaises(OSError):
                n.cleanup(self.root, True, at)
        self.assertTrue((self.root/'.retention.json').exists())
        n.cleanup(self.root, True, at)
        self.assertFalse((self.root/'.retention.json').exists())
        self.assertEqual(list((self.root/'issues').iterdir()), [])
        self.assertEqual((notes/'keep').read_text(), 'safe')
        self.assertIn('No editions', (self.root/'latest.md').read_text())

    def test_root_adoption_and_root_symlinks_are_refused(self):
        self.root.mkdir()
        (self.root/'keep').write_text('safe')
        with self.assertRaises(ValueError):
            n.publish(self.root, self.work)
        link = self.base/'link'
        link.symlink_to(self.root)
        with self.assertRaises(ValueError):
            n.publish(link, self.work)

    def test_work_retention_leaves_non_workflow_directories_alone(self):
        root, owner = n.store(self.root)
        at = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
        work = root/'.work/2026-10-09'
        work.mkdir()
        (work/'.newsletter-work.json').write_text(json.dumps({'schema': 'newsletter-work/v1', 'store_id': owner,
                                                             'created_at': (at-timedelta(days=8)).isoformat()}))
        (work/'research.json').write_text('public evidence')
        keep = root/'.work/2026-10-08'
        keep.mkdir()
        (keep/'manual.txt').write_text('unowned')
        n.cleanup(root, True, at)
        self.assertFalse(work.exists())
        self.assertTrue(keep.exists())

    def test_pending_model_attempt_requires_explicit_recovery(self):
        (self.work/'issue.json').unlink()
        (self.work/'draft.pending.json').write_text('{}')
        with patch.object(draft.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'already started'):
                draft.generate(self.work, 'draft')
            run.assert_not_called()

    def test_claude_drafts_neutral_json_and_records_its_identity(self):
        (self.work/'issue.json').unlink()
        def respond(command, **kwargs):
            self.assertEqual(command[0], 'fixture-claude')
            self.assertEqual(command[command.index('--tools')+1], '')
            self.assertIn('--strict-mcp-config', command)
            self.assertIn('--no-session-persistence', command)
            self.assertEqual(json.loads(command[command.index('--settings')+1]), {'disableAllHooks': True})
            self.assertEqual(kwargs['cwd'], self.work.resolve())
            self.assertEqual(kwargs['env']['CLAUDE_CODE_DISABLE_CLAUDE_MDS'], '1')
            self.assertEqual(kwargs['env']['MAX_STRUCTURED_OUTPUT_RETRIES'], '1')
            self.assertEqual(json.loads(kwargs['input'].decode().split('SOURCE DATA:\n', 1)[1]),
                             {'research': self.research})
            for event in [
                    {'type': 'system', 'subtype': 'init', 'model': 'claude-fixture', 'tools': ['StructuredOutput']},
                    {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'StructuredOutput'}]}},
                    {'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': self.issue}]:
                kwargs['stdout'].write((json.dumps(event)+'\n').encode())
            return subprocess.CompletedProcess(command, 0)
        with patch.object(draft.subprocess, 'run', side_effect=respond) as run:
            output = draft.generate(self.work, 'draft', claude='fixture-claude')
            self.assertEqual(json.loads(output.read_text()), self.issue)
            self.assertEqual(output, draft.generate(self.work, 'draft', claude='fixture-claude'))
            self.assertEqual(run.call_count, 1)
        receipt = json.loads((self.work/'draft.receipt.json').read_text())
        self.assertEqual(receipt['producer'], 'claude')
        self.assertEqual(receipt['model'], 'claude-fixture')

    def test_codex_review_is_separate_and_revision_bound(self):
        (self.work/'editorial-review.json').unlink()
        def respond(command, **kwargs):
            self.assertEqual(command[:2], ['fixture-codex', 'exec'])
            self.assertIn('shell_tool', command)
            self.assertIn('multi_agent', command)
            self.assertIn('web_search="disabled"', command)
            self.assertEqual(json.loads(kwargs['input'].decode().split('SOURCE DATA:\n', 1)[1]),
                             {'research': self.research, 'issue': self.issue})
            candidate = Path(command[command.index('--output-last-message')+1])
            candidate.write_text(json.dumps({'approved': True, 'problems': [], 'assessment': 'Fixture review'}))
            kwargs['stdout'].write(b'{"type":"item.completed","item":{"type":"agent_message"}}\n')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(draft.subprocess, 'run', side_effect=respond):
            output = draft.generate(self.work, 'review', codex='fixture-codex')
        review = json.loads(output.read_text())
        self.assertEqual(review['issue_sha256'], self.review['issue_sha256'])
        self.assertEqual(review['research_sha256'], self.review['research_sha256'])
        self.assertEqual(json.loads((self.work/'review.receipt.json').read_text())['producer'], 'codex')

    def test_claude_errors_missing_results_and_tool_activity_hold_output(self):
        (self.work/'issue.json').unlink()
        success = {'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': self.issue}
        for events in [[], [{'type': 'result', 'subtype': 'error', 'is_error': True}],
                       [{'type': 'result', 'subtype': 'success', 'is_error': True, 'result': 'Fixture provider refusal'}],
                       [{'type': 'result', 'subtype': 'success', 'is_error': False}],
                       [{'type': 'system', 'subtype': 'init', 'tools': ['Bash']}, success],
                       [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Bash'}]}}, success]]:
            with self.subTest(events=events):
                def respond(command, **kwargs):
                    for event in events:
                        kwargs['stdout'].write((json.dumps(event)+'\n').encode())
                    return subprocess.CompletedProcess(command, 0)
                with patch.object(draft.subprocess, 'run', side_effect=respond) as run:
                    with self.assertRaises((ValueError, RuntimeError)):
                        draft.generate(self.work, 'draft')
                    with self.assertRaisesRegex(ValueError, 'already started'):
                        draft.generate(self.work, 'draft')
                    self.assertEqual(run.call_count, 1)
                self.assertFalse((self.work/'issue.json').exists())
                (self.work/'draft.pending.json').unlink()

    def test_writer_change_cannot_reuse_a_previous_producer_receipt(self):
        (self.work/'draft.receipt.json').write_text(json.dumps({
            'producer': 'codex',
            'input_sha256': draft.hashlib.sha256(json.dumps({'research': self.research}, ensure_ascii=False).encode()).hexdigest(),
            'output_sha256': draft.hashlib.sha256((self.work/'issue.json').read_bytes()).hexdigest()}))
        with patch.object(draft.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'producer'):
                draft.generate(self.work, 'draft')
            run.assert_not_called()

    def test_explicit_feedback_is_bound_to_writer_input_and_excluded_from_review(self):
        feedback = self.base/'feedback.json'
        feedback.write_text(json.dumps({'previous_issue': self.issue, 'corrections': ['Qualify a claim']}))
        (self.work/'issue.json').unlink()
        def respond(command, **kwargs):
            payload = json.loads(kwargs['input'].decode().split('SOURCE DATA:\n', 1)[1])
            self.assertEqual(payload['revision'], json.loads(feedback.read_text()))
            result = {'type': 'result', 'subtype': 'success', 'is_error': False, 'structured_output': self.issue}
            kwargs['stdout'].write((json.dumps(result)+'\n').encode())
            return subprocess.CompletedProcess(command, 0)
        with patch.object(draft.subprocess, 'run', side_effect=respond) as run:
            draft.generate(self.work, 'draft', feedback=feedback)
            feedback.write_text(json.dumps({'previous_issue': self.issue, 'corrections': ['Changed feedback']}))
            with self.assertRaisesRegex(ValueError, 'input/output changed'):
                draft.generate(self.work, 'draft', feedback=feedback)
            with self.assertRaisesRegex(ValueError, 'only by the copywriter'):
                draft.generate(self.work, 'review', feedback=feedback)
            self.assertEqual(run.call_count, 1)

    def test_malformed_feedback_fails_before_model_invocation(self):
        feedback = self.base/'feedback.json'
        for value in [[], {}, {'previous_issue': {}, 'corrections': []},
                      {'previous_issue': {}, 'corrections': ['']}]:
            feedback.write_text(json.dumps(value))
            with patch.object(draft.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Revision JSON'):
                    draft.generate(self.work, 'draft', feedback=feedback)
                run.assert_not_called()

    def test_headless_environment_permissions_and_names(self):
        env = self.base/'environment.json'
        env.write_text(json.dumps({'EXA_API_KEY': 'fixture-key'}))
        env.chmod(0o600)
        self.assertEqual(host.environment(env)['EXA_API_KEY'], 'fixture-key')
        env.chmod(0o644)
        with self.assertRaises(ValueError):
            host.environment(env)
        env.chmod(0o600)
        env.write_text(json.dumps({'HOME': '/arbitrary'}))
        with self.assertRaises(ValueError):
            host.environment(env)

    def test_research_reuses_responses_and_rejects_changed_configuration(self):
        config = {'search_command': ['fixture-search', '--after-date', '{window_start_date}'], 'providers': ['exa'],
                  'topics': [{'name': t, 'query': t} for t in ['Research', 'Agents', 'Retrieval']],
                  'domains': ['example.org'], 'sources_per_topic_provider': 3, 'max_original_pages': 0}
        responses = []
        for topic in range(3):
            native = {'results': [{'url': f'https://example.org/{topic}-{i}', 'title': 'A source',
                                 'highlights': ['An exact public excerpt.']} for i in range(3)]}
            responses.append(subprocess.CompletedProcess([], 0, json.dumps({'exa': {'response': native}}).encode()))
        work = self.base/'research-work'
        with patch.object(research.subprocess, 'run', side_effect=responses) as run:
            first = research.collect(config, work)
            self.assertEqual(run.call_count, 3)
            start = datetime.fromisoformat(first['window_start']).date().isoformat()
            self.assertTrue(all(call.args[0][1:3] == ['--after-date', start] for call in run.call_args_list))
            self.assertEqual(first, research.collect(config, work))
            self.assertEqual(run.call_count, 3)
            with self.assertRaisesRegex(ValueError, 'configuration changed'):
                research.collect(dict(config, max_original_pages=1), work)

    def test_research_failed_search_is_not_automatically_retried(self):
        config = {'search_command': ['fixture-search'], 'topics': [{'name': 'Research', 'query': 'research'}]}
        failure = subprocess.CompletedProcess([], 2, b'{"exa":{"error":"unauthorized"}}')
        with patch.object(research.subprocess, 'run', return_value=failure) as run:
            for attempt in range(2):
                with self.assertRaisesRegex(RuntimeError, 'Search failed'):
                    research.collect(config, self.base/'failed-search')
            self.assertEqual(run.call_count, 1)

    def test_source_budget_cannot_starve_later_topics(self):
        topics = [{'name': str(i)} for i in range(17)]
        sources = {f'{topic}-{i}': {'topics': [str(topic)]} for topic in range(17) for i in range(4)}
        selected = research.balanced_sources(sources, topics, 48)
        self.assertEqual(len(selected), 48)
        self.assertEqual({topic for source in selected.values() for topic in source['topics']}, {str(i) for i in range(17)})
        self.assertEqual(list(selected)[:17], [f'{i}-0' for i in range(17)])

    def test_default_topic_sweep_searches_and_retains_every_section(self):
        config = json.loads((SKILL/'assets/config.example.json').read_text())
        self.assertEqual(len(config['topics']), 17)
        config.update(search_command=['fixture-search'], domains=['example.org'], max_original_pages=0,
                      max_sources=17)
        responses = []
        for index in range(17):
            rows = [{'url': f'https://example.org/{index}/{rank}', 'highlights': ['A source body. '*1000]}
                    for rank in range(3)]
            rows.insert(0, {'url': f'https://example.org/{index}/empty', 'highlights': []})
            responses.append(subprocess.CompletedProcess([], 0, json.dumps({'exa': {'response': {'results': rows}}}).encode()))
        with patch.object(research.subprocess, 'run', side_effect=responses) as run:
            result = research.collect(config, self.base/'full-sweep')
        self.assertEqual(run.call_count, 17)
        self.assertEqual(len(result['sources']), 17)
        self.assertTrue(all(row['retained_sources'] == 1 for row in result['coverage']))
        self.assertEqual({t for source in result['sources'] for t in source['topics']}, set(result['topics']))
        self.assertTrue(all(len(source['content']) <= config['source_chars'] for source in result['sources']))

    def test_research_configuration_bounds_stop_before_search(self):
        for config in [{'topics': [{'name': str(i)} for i in range(25)]},
                       {'topics': [{'name': 'Research'}], 'max_sources': 61},
                       {'topics': [{'name': 'Research'}], 'source_chars': 100000}]:
            with patch.object(research.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'bounds'):
                    research.collect(config, self.base/'invalid')
                run.assert_not_called()

    def test_cleanup_cli_does_not_adopt_an_empty_directory(self):
        self.root.mkdir()
        result = subprocess.run([os.sys.executable, str(SKILL/'scripts/newsletter.py'), 'cleanup',
                                 '--root', str(self.root)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_completed_daily_edition_skips_paid_acquisition(self):
        today = datetime.now(n.ZoneInfo('America/Detroit')).date().isoformat()
        n.publish(self.root, self.work, today)
        result = subprocess.run([os.sys.executable, str(SKILL/'scripts/newsletter.py'), 'collect',
                                 '--config', '/missing-config.json'],
                                capture_output=True, env=dict(os.environ, NEWSLETTER_WORK='',
                                                              HOME=str(self.base), NEWSLETTER_ROOT='~/store'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'Edition already published', result.stdout)

    def test_citation_preserves_exact_source_whitespace(self):
        self.research['sources'][0]['content'] = self.research['sources'][0]['content'].replace('enough context', 'enough\ncontext')
        self.review['research_sha256'] = n.checksum(json.dumps(self.research, ensure_ascii=False, sort_keys=True).encode())
        with self.assertRaisesRegex(ValueError, 'Quotation not present'):
            n.validate(self.issue, self.research, self.review)

    def test_markdown_keeps_multiline_quotations_inside_the_source_block(self):
        self.issue['stories'][0]['citations'][0]['quote'] = 'First source line.\nSecond source line.'
        rendered = n.markdown(self.issue, self.research)
        self.assertIn('  > First source line.\n  > Second source line.', rendered)

    def test_current_news_precedes_background_without_inventing_freshness(self):
        self.issue['stories'][0]['event_date'] = '2026-10-14'
        self.issue['stories'][1]['event_date'] = '2026-10-15'
        self.issue['stories'][4]['event_date'] = '2026-10-18'
        self.issue['stories'][5]['event_date'] = '2026-10-19'
        view = n.reading(self.issue, self.research)
        self.assertEqual([s['id'] for s in view['current']], ['story-4'])
        text = n.markdown(self.issue, self.research)
        self.assertLess(text.index('### Story 4'), text.index('### Story 0'))
        self.assertIn('[Story 4](#story-4)', text)
        self.research['sources'][0]['published_at'] = '2026-10-15T10:00:00Z'
        self.assertEqual([s['id'] for s in n.reading(self.issue, self.research)['current']], ['story-1', 'story-4'])

    def test_briefs_are_compact_but_deep_dives_keep_analysis(self):
        self.issue['stories'][2]['technical_detail'] = 'Supporting brief analysis not shown in the reading copy.'
        text = n.markdown(self.issue, self.research)
        self.assertNotIn(self.issue['stories'][2]['technical_detail'], text)
        self.assertIn(self.issue['stories'][0]['technical_detail'], text)
        self.assertEqual(text.count('#### Under the hood'), 2)
        self.assertIn(self.issue['stories'][2]['limitations'], text)
        self.assertNotIn('Today in 60 seconds', text)
        self.assertIn('Reading shortlist', text)

    def test_oversized_briefs_fail_instead_of_losing_words_in_rendering(self):
        self.issue['stories'][2]['summary'] = 'word ' * 101
        with self.assertRaisesRegex(ValueError, '100 words'):
            n.validate(self.issue, self.research, self.review)

    def test_source_urls_and_exact_quotations_are_deduplicated(self):
        self.research['sources'].append(dict(self.research['sources'][0], id='alias'))
        quote = self.issue['stories'][0]['citations'][0]['quote']
        self.issue['stories'][0]['citations'].append({'source_id': 'alias', 'quote': quote})
        view = n.reading(self.issue, self.research)
        self.assertEqual(len(view['references']), 1)
        self.assertEqual(view['numbers']['alias'], view['numbers']['source'])
        text = n.markdown(self.issue, self.research)
        self.assertEqual(text.count('  > '+quote), 1)
        self.assertEqual(text.count('### [1: Original source]'), 1)

    def test_broken_source_title_uses_url_without_changing_evidence(self):
        broken = r'0.64314C\__color_backend_reset: broken title'
        self.research['sources'][0]['title'] = broken
        view = n.reading(self.issue, self.research)
        self.assertEqual(view['references'][0]['title'], 'https://example.org/article')
        self.assertNotIn(broken, n.markdown(self.issue, self.research))
        self.assertEqual(self.research['sources'][0]['title'], broken)

    def test_reference_labels_preserve_source_text_and_accept_both_separators(self):
        self.research['sources'].append(dict(self.research['sources'][0], id='other', url='https://example.org/other'))
        self.issue['editorial'] = 'Literal source. References [other, source] and [source; other]. Kept [note].'
        text = n.markdown(self.issue, self.research)
        linked = '[[1](#source-1); [2](#source-2)]'
        self.assertIn(f'Literal source. References {linked} and {linked}. Kept [note].', text)
        self.assertIn('<a id="source-2"></a>', text)
        self.assertIn(self.issue['stories'][0]['citations'][0]['quote'], text)

    def test_inline_references_replace_the_story_source_row(self):
        self.issue['stories'][2]['summary'] = 'A concrete mechanism [source].'
        text = n.markdown(self.issue, self.research)
        self.assertIn('A concrete mechanism [[1](#source-1)].', text)
        # Five uncited stories keep a fallback row; the inline-cited brief does not repeat it.
        self.assertEqual(text.count('Sources: [[1](#source-1)]'), 5)

    def test_quotation_running_into_an_extracted_heading_fails(self):
        debris = 'Based on customer benchmarking of the serving recipe.\n\n \n\n### **Scaling inference requires system-level optimization**'
        # A trailing code comment is legitimate evidence, not a page heading.
        code = 'pipe.load_components(dtype=dtype)\n\n# no pipe.to("cuda"): the manager handles device placement'
        for quote, valid in ((debris, False), (code, True)):
            self.research['sources'][0]['content'] = quote
            for story in self.issue['stories']:
                story['citations'][0]['quote'] = quote
            self.review.update(issue_sha256=n.checksum(json.dumps(self.issue, ensure_ascii=False, sort_keys=True).encode()),
                               research_sha256=n.checksum(json.dumps(self.research, ensure_ascii=False, sort_keys=True).encode()))
            if valid:
                n.validate(self.issue, self.research, self.review)
            else:
                with self.assertRaisesRegex(ValueError, 'extracted heading'):
                    n.validate(self.issue, self.research, self.review)

    def test_host_forwards_isolated_home_to_scheduler_children(self):
        env = self.base/'environment.json'
        env.write_text('{"EXA_API_KEY":"fixture"}')
        env.chmod(0o600)
        output = self.base/'forwarding.json'
        fake = self.base/'fake-dagu'
        script = ('import os,json\nfrom pathlib import Path\n'
                  f'Path({str(output)!r}).write_text(json.dumps({{k:os.environ.get(k) for k in ["DAGU_HOME","DAGU_DAGS_DIR"]}}))\n')
        fake.write_text('#!/bin/sh\nexec '+shlex.join([os.sys.executable, '-c', script])+' "$@"\n')
        fake.chmod(0o700)
        result = subprocess.run([os.sys.executable, str(SKILL/'scripts/host.py'), '--environment', str(env),
                                 '--dagu', str(fake), '--dagu-home', str(self.base/'dagu'),
                                 '--dags', str(self.base/'dags')], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text()), {'DAGU_HOME': str(self.base/'dagu'), 'DAGU_DAGS_DIR': str(self.base/'dags')})


if __name__ == '__main__':
    unittest.main()
