#!/usr/bin/env python3
"""Start an explicitly selected Dagu scheduler with owner-only local variables."""
import argparse
import json
import os
from pathlib import Path
import stat


def environment(path):
    if path.is_symlink():
        raise ValueError('Environment file must not be a symlink')
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 65536:
        raise ValueError('Environment file must be owned by this user, mode 0600 and bounded')
    values = json.loads(path.read_text())
    if not isinstance(values, dict) or set(values) - {'EXA_API_KEY', 'PARALLEL_API_KEY', 'PATH'}:
        raise ValueError('Only provider keys and PATH are accepted')
    if not all(isinstance(v, str) and '\x00' not in v for v in values.values()):
        raise ValueError('Environment values must be strings without NUL')
    return dict(os.environ, **values)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--environment', type=Path, required=True)
    p.add_argument('--dagu', required=True)
    p.add_argument('--dagu-home', required=True)
    p.add_argument('--dags', required=True)
    a = p.parse_args()
    env = environment(a.environment)
    env.update(DAGU_HOME=a.dagu_home, DAGU_DAGS_DIR=a.dags)
    os.execvpe(a.dagu, [a.dagu, 'scheduler', '--dagu-home', a.dagu_home, '--dags', a.dags], env)
