from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('tmux'), 'requires tmux')
class PrivateSocket(unittest.TestCase):
    def test_capture_timeout_and_discovery(self):
        with tempfile.TemporaryDirectory(prefix='tmux-fixture-') as directory:
            socket = str(Path(directory) / 'socket')
            tmux = ['tmux', '-S', socket]
            try:
                subprocess.run(tmux + ['new-session', '-d', '-s', 'fixture',
                                      '/bin/sh', '-c', 'printf "READY fixture\\n"; sleep 20'],
                               check=True, capture_output=True)
                helper = ['bash', str(ROOT / 'scripts/wait-for-text.sh'),
                          '-S', socket, '-t', 'fixture:0.0', '-T', '1']
                for pattern, code in [('READY', 0), ('NEVER_PRESENT', 1)]:
                    result = subprocess.run(helper + ['-p', pattern], capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, code, result.stderr)
                result = subprocess.run(['bash', str(ROOT / 'scripts/find-sessions.sh'),
                                         '-S', socket, '-q', 'fixture'], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b'fixture', result.stdout)
                result = subprocess.run(['bash', str(ROOT / 'scripts/wait-for-text.sh'), '-S'],
                                        capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
            finally:
                subprocess.run(tmux + ['kill-server'], capture_output=True)


if __name__ == '__main__':
    unittest.main()
