#!/usr/bin/env python3
"""Launch one independently callable tool with installation-local state."""
import os
from pathlib import Path
import sys

prefix = Path(__file__).resolve().parents[1]
command = Path(sys.argv[0]).name
env = os.environ.copy()
env['AGENT_KNOWLEDGE_HOME'] = str(prefix)
env['SOURCE_INSIGHTS_LIBRARY'] = env.get('SOURCE_INSIGHTS_LIBRARY', str(prefix / 'knowledge/sources'))
env['SOURCE_INSIGHTS_INDEX_MODE'] = env.get('SOURCE_INSIGHTS_INDEX_MODE', 'keyword')
env['SESSION_SEARCH_DB'] = env.get('SESSION_SEARCH_DB', str(prefix / 'state/session-search.sqlite'))
env['BKD_HOME'] = env.get('BKD_HOME', str(prefix / 'state/bookmarks'))
env['DISTILLER_COVER_CACHE'] = env.get('DISTILLER_COVER_CACHE', str(prefix / 'state/covers'))
env['PATH'] = str(prefix / 'bin') + os.pathsep + env.get('PATH', '')
env['PYTHONPATH'] = str(prefix / 'lib')
python = str(prefix / 'runtimes/source-insights/bin/python')
scripts = {
    'source-insights': prefix / 'skills/source-insights/scripts/sources.py',
    'session-search': prefix / 'skills/session-search/scripts/session-search',
    'knowledge-intake': prefix / 'libexec/intake.py',
}
if command in scripts:
    argv = [python, str(scripts[command]), *sys.argv[1:]]
else:
    argv = [str(prefix / 'libexec/native' / command), *sys.argv[1:]]
os.execve(argv[0], argv, env)
