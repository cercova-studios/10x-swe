"""The recipe must not run its consumer after either producer fails."""
import json, os, subprocess, tempfile
from pathlib import Path
script=Path('examples/compose-search.zsh').resolve()
with tempfile.TemporaryDirectory(prefix='bkd-compose-test-') as temp:
 root=Path(temp);marker=root/'consumer-ran'
 def tool(name,body):
  p=root/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
 env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'])
 tool('python3',"printf '%s\\n' '{\"schema\":\"knowledge-snapshot/v1\",\"corpus\":\"insights\"}'")
 tool('skill-search',"printf '%s\\n' '{\"schema\":\"knowledge-snapshot/v1\",\"corpus\":\"skills\"}'")
 tool('bkd',f"cat >/dev/null; touch '{marker}'; printf '%s\\n' '{{\"ok\":true}}'")
 def run():return subprocess.run(['zsh',str(script),'fixture'],env=env,capture_output=True,text=True)
 r=run();assert r.returncode==0,r.stderr
 assert json.loads(r.stdout)['ok'] and marker.exists()
 marker.unlink()
 tool('skill-search',"printf '%s\\n' 'partial record'; exit 7")
 r=run();assert r.returncode!=0 and not r.stdout and not marker.exists(),(r.returncode,r.stdout,r.stderr)
 tool('python3',"printf '%s\\n' 'partial record'; exit 8")
 r=run();assert r.returncode!=0 and not r.stdout and not marker.exists(),(r.returncode,r.stdout,r.stderr)
 print('PASS: explicit recipe stages records; either producer failure prevents consumer execution')
