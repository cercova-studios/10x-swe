"""Offline helper and recovery fixtures. No real credentials or network calls."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'FAKE_TOKEN_NOT_REAL'
SECRET = 'fixture-secret-not-real'

CURL = r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
root=Path(os.environ['FIXTURE']);calls=root/'curl.jsonl'
args=sys.argv[1:];data=sys.stdin.read() if '--config' in args or '@-' in args else ''
assert 'FAKE_TOKEN_NOT_REAL' not in ' '.join(args)
assert 'fixture-secret-not-real' not in ' '.join(args)
assert 'CLOUDFLARE_API_TOKEN' not in os.environ
prior=calls.read_text().splitlines() if calls.exists() else []
responses=json.loads((root/'responses.json').read_text());response=responses[len(prior)]
url=next((a for a in args if a.startswith('https://')),'')
assert url.startswith(('https://api.cloudflare.com/','https://challenges.cloudflare.com/'))
with calls.open('a') as f:f.write(json.dumps({'url':url,'args':args,'has_input':bool(data)})+'\n')
if response.get('exit'):sys.exit(response['exit'])
status=response.get('status',200)
if '--fail' in args and status>=400:sys.exit(22)
body=response.get('body',{})
if '--output' not in args:sys.stdout.write(body if isinstance(body,str) else json.dumps(body))
if '--write-out' in args:sys.stdout.write(('\n' if '\n' in args[args.index('--write-out')+1] else '')+str(status))
'''
WRANGLER = r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
root=Path(os.environ['FIXTURE']);args=sys.argv[1:]
with (root/'wrangler.jsonl').open('a') as f:f.write(json.dumps(args)+'\n')
if args==['--version']:print(os.environ.get('FIXTURE_VERSION','4.109.0'))
elif args==['whoami','--json']:print(json.dumps({'accounts':[{'id':'acct-a'},{'id':'acct-b'}]}))
elif args[:2]==['secret','list']:
 if os.environ.get('FIXTURE_NO_WORKER'):sys.exit(1)
 print(json.dumps([{'name':'TURNSTILE_SECRET'}]))
elif args[:3]==['turnstile','widget','get']:
 print(json.dumps({'sitekey':os.environ.get('FIXTURE_SITEKEY','site'),'secret':'fixture-secret-not-real','domains':['example.com'],'clearance_level':'managed'}))
elif args[:2]==['secret','put']:
 assert sys.stdin.read()=='fixture-secret-not-real'
 (root/'secret-written').write_text('fixture write only')
else:sys.exit(99)
'''
GIT = r'''#!/usr/bin/env python3
import json,os,shutil,sys
from pathlib import Path
root=Path(os.environ['FIXTURE']);args=sys.argv[1:]
assert not any(k in os.environ for k in ['CLOUDFLARE_API_TOKEN','WIDGET_SECRET','GITHUB_TOKEN'])
with (root/'git.jsonl').open('a') as f:f.write(json.dumps(args)+'\n')
if os.environ.get('FIXTURE_CLONE_FAIL'):sys.exit(1)
if 'clone' in args:
 dest=Path(args[-1])/'skills/turnstile-spin';shutil.copytree(root/'upstream',dest)
elif 'sparse-checkout' not in args:sys.exit(99)
'''

class Helpers(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name).resolve();self.bin=self.work/'bin';self.bin.mkdir()
        self.project=self.work/'project';self.project.mkdir()
        for name,code in [('curl',CURL),('wrangler',WRANGLER),('git',GIT)]:
            p=self.bin/name;p.write_text(code);p.chmod(0o755)
        self.env={'PATH':str(self.bin)+':'+os.environ['PATH'],'FIXTURE':str(self.work),'TMPDIR':str(self.work),'CLOUDFLARE_API_TOKEN':TOKEN,'CLOUDFLARE_ACCOUNT_ID':'acct-a'}
        self.responses([])
    def responses(self,values):
        (self.work/'responses.json').write_text(json.dumps(values))
        (self.work/'curl.jsonl').unlink(missing_ok=True)
    def run_helper(self,name,args=(),stdin='',extra=None):
        return subprocess.run(['bash',str(ROOT/'scripts'/name),*args],input=stdin,text=True,capture_output=True,cwd=self.project,env=self.env|(extra or {}),timeout=15)
    def metadata(self,**changes):
        return {'success':True,'result':{'sitekey':'site','secret':SECRET,'domains':['example.com'],'clearance_level':'managed'}|changes}
    def validate(self,metadata=None,verify=None):
        self.responses([{'body':metadata or self.metadata()},{'body':verify or {'success':False,'error-codes':['invalid-input-response']}}])
        return self.run_helper('validate.sh',['--sitekey','site','--account-id','acct-a','--expected-domains','["example.com"]'],SECRET)
    def test_validate_success_and_redaction(self):
        r=self.validate();self.assertEqual(r.returncode,0,r.stderr)
        self.assertNotIn(SECRET,r.stdout+r.stderr);self.assertNotIn(TOKEN,r.stdout+r.stderr)
    def test_validate_metadata_mismatch_and_bad_secret(self):
        for change in [{'sitekey':'other'},{'domains':['wrong.example']},{'clearance_level':'invalid'},{'secret':'other'}]:
            r=self.validate(self.metadata(**change));self.assertNotEqual(r.returncode,0,change)
            self.assertEqual(len((self.work/'curl.jsonl').read_text().splitlines()),1)
    def test_validate_rejects_siteverify_failure(self):
        for response in [{'success':True},{'success':False,'error-codes':['invalid-input-secret']},'not json']:
            self.assertNotEqual(self.validate(verify=response).returncode,0)
    def test_validate_missing_args_and_invalid_domains(self):
        for args in [[],['--sitekey'],['--sitekey','site','--account-id','acct-a','--expected-domains','[]']]:
            self.assertNotEqual(self.run_helper('validate.sh',args,SECRET).returncode,0)
        self.assertFalse((self.work/'curl.jsonl').exists())
    def test_validate_network_failure(self):
        self.responses([{'exit':7}]);r=self.run_helper('validate.sh',['--sitekey','site','--account-id','acct-a','--expected-domains','["example.com"]'],SECRET)
        self.assertNotEqual(r.returncode,0)
    def test_auth_missing_token_and_scope(self):
        r=self.run_helper('auth-probe.sh',extra={'CLOUDFLARE_API_TOKEN':''})
        self.assertEqual(json.loads(r.stdout)['status'],'missing_token')
        self.responses([{'status':403,'body':{'success':False}}])
        self.assertEqual(json.loads(self.run_helper('auth-probe.sh').stdout)['status'],'missing_scope')
    def test_auth_ok_and_malformed_upstream(self):
        for body,status,expected in [({'success':False},400,'ok'),('bad-json',400,'upstream_failure')]:
            self.responses([{'status':status,'body':body}])
            self.assertEqual(json.loads(self.run_helper('auth-probe.sh').stdout)['status'],expected)
    def test_auth_multiple_accounts_and_mismatch(self):
        common={'WRANGLER_BIN':str(self.bin/'wrangler'),'WRANGLER_VERSION':'4.109.0','PROJECT_ROOT':str(self.project)}
        r=self.run_helper('auth-probe.sh',extra=common|{'CLOUDFLARE_ACCOUNT_ID':''})
        self.assertEqual(json.loads(r.stdout)['status'],'multiple_accounts')
        r=self.run_helper('auth-probe.sh',extra=common|{'CLOUDFLARE_ACCOUNT_ID':'wrong'})
        self.assertEqual(json.loads(r.stdout)['status'],'account_mismatch')
        self.assertFalse((self.work/'curl.jsonl').exists())
    def test_auth_rejects_project_binary_and_version_mismatch(self):
        p=self.project/'wrangler';p.write_text(WRANGLER);p.chmod(0o755)
        r=self.run_helper('auth-probe.sh',extra={'WRANGLER_BIN':str(p),'WRANGLER_VERSION':'4.109.0','PROJECT_ROOT':str(self.project)})
        self.assertEqual(json.loads(r.stdout)['reason'],'project_local_wrangler')
        r=self.run_helper('auth-probe.sh',extra={'WRANGLER_BIN':str(self.bin/'wrangler'),'WRANGLER_VERSION':'4.108.0'})
        self.assertEqual(json.loads(r.stdout)['reason'],'wrangler_version_mismatch')
    def test_auth_failed_cleanup_cannot_report_ok(self):
        self.responses([{'body':self.metadata()},{'status':500}])
        r=self.run_helper('auth-probe.sh');self.assertEqual(json.loads(r.stdout)['status'],'upstream_failure')
    def test_auth_successful_cleanup(self):
        self.responses([{'body':self.metadata()},{'status':204}])
        self.assertEqual(json.loads(self.run_helper('auth-probe.sh').stdout)['status'],'ok')
    def test_create_success_and_invalid_inputs(self):
        args=['--account-id','acct-a','--name','fixture','--domains','example.com']
        self.responses([{'body':self.metadata()}]);r=self.run_helper('widget-create.sh',args)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['secret'],SECRET)
        for extra in [['--mode','unsupported'],['--domains',',,']]:
            self.responses([]);self.assertNotEqual(self.run_helper('widget-create.sh',args+extra).returncode,0)
            self.assertFalse((self.work/'curl.jsonl').exists())
    def test_create_bad_upstream(self):
        for response in [{'body':'not json'},{'body':{'success':False}},{'exit':7}]:
            self.responses([response]);r=self.run_helper('widget-create.sh',['--account-id','acct-a','--name','fixture','--domains','example.com'])
            self.assertNotEqual(r.returncode,0);self.assertNotIn(TOKEN,r.stdout+r.stderr)
    def test_persist_containment_and_no_overwrite(self):
        occupied=self.project/'occupied';occupied.mkdir();(occupied/'keep').write_text('keep')
        outside=self.work/'outside';outside.mkdir();(self.project/'escape').symlink_to(outside,target_is_directory=True)
        for path in [str(outside/'SKILL.md'),'escape/SKILL.md','occupied/SKILL.md','rules.md']:
            self.assertNotEqual(self.run_helper('persist-skill.sh',['--path',path]).returncode,0)
        self.assertEqual((occupied/'keep').read_text(),'keep');self.assertFalse((self.work/'git.jsonl').exists())
    def test_persist_fixture_and_clone_failure(self):
        source=self.work/'upstream';(source/'scripts').mkdir(parents=True);(source/'SKILL.md').write_text('fixture');(source/'scripts/example.sh').write_text('#!/bin/bash\nexit 0\n')
        r=self.run_helper('persist-skill.sh',['--path','.agents/skills/fixture/SKILL.md'])
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual((self.project/'.agents/skills/fixture/SKILL.md').read_text(),'fixture')
        r=self.run_helper('persist-skill.sh',['--path','.agents/skills/failed/SKILL.md'],extra={'FIXTURE_CLONE_FAIL':'1'})
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.project/'.agents/skills/failed').exists())
    def recovery(self,extra=None):
        source=(ROOT/'references/existing-widget.md').read_text()
        blocks=re.findall(r'```bash\n(.*?)```',source,re.S);code=textwrap.dedent(blocks[1])
        env=self.env|{'PROJECT_ROOT':str(self.project),'WRANGLER_BIN':str(self.bin/'wrangler'),'WRANGLER_VERSION':'4.109.0','ACCOUNT_ID':'acct-a','SITEKEY':'site','EXPECTED_DOMAINS_JSON':'["example.com"]','SECRET_NAME':'TURNSTILE_SECRET','WORKER_NAME':'fixture-worker'}|(extra or {})
        # This flow uses a preauthenticated Wrangler, not an API-token environment.
        env.pop('CLOUDFLARE_API_TOKEN',None)
        return subprocess.run(['bash','-c',code],input='',env=env,cwd=self.project,text=True,capture_output=True,timeout=15)
    def test_recovery_validates_before_sink(self):
        self.responses([{'body':{'success':False,'error-codes':['invalid-input-response']}}])
        r=self.recovery();self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((self.work/'secret-written').exists());self.assertNotIn(SECRET,r.stdout+r.stderr)
    def test_recovery_rejects_metadata_and_secret_errors_before_sink(self):
        for extra,response in [({'FIXTURE_SITEKEY':'wrong'},{'success':False,'error-codes':['invalid-input-response']}),({},{'success':False,'error-codes':['invalid-input-secret']})]:
            self.responses([{'body':response}]);r=self.recovery(extra)
            self.assertNotEqual(r.returncode,0);self.assertFalse((self.work/'secret-written').exists())
    def test_recovery_version_and_missing_worker_stop_before_getter(self):
        for extra in [{'FIXTURE_VERSION':'4.108.0'},{'FIXTURE_NO_WORKER':'1'}]:
            (self.work/'wrangler.jsonl').unlink(missing_ok=True)
            self.assertNotEqual(self.recovery(extra).returncode,0)
            calls=[json.loads(s) for s in (self.work/'wrangler.jsonl').read_text().splitlines()]
            self.assertFalse(any(c[:3]==['turnstile','widget','get'] for c in calls))
            self.assertFalse((self.work/'secret-written').exists())

if __name__=='__main__':unittest.main()
