#!/usr/bin/env python3
"""Run a bounded, synthetic reviewer smoke test without publication."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def run(work, codex):
    skill = Path(__file__).resolve().parents[1]
    cases = json.loads((skill/'assets/review-cases.json').read_text())
    work.mkdir(parents=True, exist_ok=False)
    results = []
    for index, case in enumerate(cases, 1):
        target = work/f'case-{index:02d}'
        target.mkdir()
        source = {'id': 'source', 'url': 'https://example.org/synthetic', 'title': 'Synthetic evaluation',
                  'published_at': None, 'content': case['evidence'], 'coverage': 'synthetic fixture'}
        research = {'schema': 'newsletter-research/v1', 'window_start': '2026-10-15T08:00:00+00:00',
                    'window_end': '2026-10-18T08:00:00+00:00', 'topics': ['Evaluation'], 'sources': [source]}
        story = {'id': 'test-story', 'topic': 'Evaluation', 'kind': 'brief', 'event_date': '',
                 'headline': 'A bounded engineering observation', 'summary': case['copy'],
                 'technical_detail': '', 'why_it_matters': '', 'relevance': '',
                 'limitations': 'Synthetic observation; broader effects are untested.',
                 'citations': [{'source_id': 'source', 'quote': case['evidence']}]}
        issue = {'title': 'Synthetic review example', 'standfirst': 'An engineering observation [source].',
                 'editorial': 'A bounded observation, with wider effects untested [source].', 'stories': [story]}
        for name, value in [('research.json', research), ('issue.json', issue)]:
            (target/name).write_text(json.dumps(value))
        subprocess.run([sys.executable, str(skill/'scripts/draft.py'), 'review', '--work', str(target.resolve()),
                        '--codex', codex], check=True, stdout=sys.stderr, timeout=930)
        review = json.loads((target/'editorial-review.json').read_text())
        results.append({'id': case['id'], 'expected_approved': case['approved'],
                        'approved': review['approved'], 'expected_reason': case['reason'],
                        'problems': review['problems'], 'assessment': review['assessment']})
    report = {'results': results, 'label_matches': sum(r['approved'] == r['expected_approved'] for r in results),
              'cases': len(results), 'rationale_review': 'pending human inspection',
              'scope': 'synthetic smoke test; not human calibration or publication approval'}
    (work/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True, help='fresh output directory; invokes six Codex reviews')
    p.add_argument('--codex', default='codex')
    a = p.parse_args()
    try:
        report = run(a.work, a.codex)
        print(json.dumps(report))
        sys.exit(0 if report['label_matches'] == report['cases'] else 1)
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
