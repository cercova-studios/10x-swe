"""Installation ownership, failed readiness and concurrency boundaries."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
bootstrap=load('bootstrap',REPO/'plugins/knowledge/bootstrap.py')


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def test_plan_has_no_writes(self):
        target=self.root/'absent'
        p=subprocess.run([sys.executable,str(REPO/'plugins/knowledge/bootstrap.py'),'plan','--prefix',str(target)],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertFalse(target.exists())
        self.assertIn('Kindle delivery',json.loads(p.stdout)['excluded'])
    def test_owned_retries_reject_conflicts_and_changed_source(self):
        target=self.root/'owned';bootstrap.owned(target,'a'*64);bootstrap.owned(target,'a'*64)
        with self.assertRaisesRegex(ValueError,'different source'): bootstrap.owned(target,'b'*64)
        conflict=self.root/'existing';conflict.mkdir();(conflict/'valuable').write_text('retain')
        with self.assertRaisesRegex(ValueError,'unowned'): bootstrap.owned(conflict,'a'*64)
        self.assertEqual((conflict/'valuable').read_text(),'retain')
        alias=self.root/'alias';alias.symlink_to(target)
        with self.assertRaisesRegex(ValueError,'symlink'): bootstrap.owned(alias,'a'*64)
    def test_failed_setup_is_not_readiness_and_tampered_artifacts_fail(self):
        target=self.root/'owned';bootstrap.owned(target,'a'*64)
        with self.assertRaisesRegex(ValueError,'No completed'): bootstrap.doctor(target,verify=False)
        (target/'artifact').write_text('changed')
        (target/'installation.json').write_text(json.dumps({'artifacts':{'artifact':'a'*64}}))
        with self.assertRaisesRegex(ValueError,'artifacts changed'): bootstrap.doctor(target,verify=False)
    def test_source_tree_install_is_rejected_before_write(self):
        with self.assertRaisesRegex(ValueError,'outside the source'): bootstrap.setup(REPO/'never-create-this')
        self.assertFalse((REPO/'never-create-this').exists())
    def test_incomplete_setup_still_requires_build_tools_and_retains_no_receipt(self):
        target=self.root/'missing-tools'
        for _ in range(2):
            p=subprocess.run([sys.executable,str(REPO/'plugins/knowledge/bootstrap.py'),'setup','--prefix',str(target)],
                             env=dict(os.environ,PATH=str(self.root/'no-tools')),capture_output=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn(b'Missing build prerequisite: cargo',p.stderr)
            self.assertFalse((target/'installation.json').exists())


if __name__=='__main__': unittest.main()
