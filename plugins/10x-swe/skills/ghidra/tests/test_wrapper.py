import os, pathlib, subprocess, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
class Wrapper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d = pathlib.Path(self.tmp.name)
        support = self.d/'ghidra/support'; support.mkdir(parents=True)
        self.log = self.d/'args'
        headless = support/'analyzeHeadless'
        headless.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$STUB_LOG"\ntouch "$1/$2.gpr"\nexit "${STUB_EXIT:-0}"\n'); headless.chmod(0o755)
        self.binary=self.d/'test binary'; self.binary.write_text('fixture')
        self.env=dict(os.environ, GHIDRA_HOME=str(support.parent), STUB_LOG=str(self.log))
    def run_wrapper(self,*args):
        return subprocess.run(['bash',str(ROOT/'scripts/ghidra-analyze.sh'),*map(str,args)],env=self.env,text=True,capture_output=True)
    def test_help_without_discovery(self):
        self.env['GHIDRA_HOME']='/missing'
        result=self.run_wrapper('--help'); self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(self.log.exists())
    def test_invalid_arguments(self):
        for args in [('-o',),('-a','orphan'),('--project-name','../escape',str(self.binary)),(str(self.binary),str(self.binary))]:
            self.assertNotEqual(self.run_wrapper(*args).returncode,0,args)
        self.assertFalse(self.log.exists())
    def test_script_error_zero_exit(self):
        stub=self.d/'ghidra/support/analyzeHeadless'
        stub.write_text('#!/bin/bash\necho "ERROR REPORT SCRIPT ERROR: failed"\nexit 0\n')
        self.assertNotEqual(self.run_wrapper('-o',self.d/'out',self.binary).returncode,0)
    def test_error_word_in_target_is_not_failure(self):
        stub=self.d/'ghidra/support/analyzeHeadless'
        stub.write_text('#!/bin/bash\necho "INFO Processing ERROR.bin"\nexit 0\n')
        self.assertEqual(self.run_wrapper('-o',self.d/'out',self.binary).returncode,0)
    def test_default_summary(self):
        r=self.run_wrapper('-o',self.d/'out',self.binary)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('ExportSummary.java',self.log.read_text())
    def test_reuse_and_identity(self):
        args=['--project-dir',self.d,'--project-name','retained','-o',self.d/'out']
        r=self.run_wrapper(*args,'--keep-project',self.binary); self.assertEqual(r.returncode,0,r.stderr)
        r=self.run_wrapper(*args,'--reuse',self.binary); self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('-process',self.log.read_text()); self.assertIn('-noanalysis',self.log.read_text()); self.assertNotIn('-import',self.log.read_text())
        self.binary.write_text('changed')
        self.assertNotEqual(self.run_wrapper(*args,'--reuse',self.binary).returncode,0)
    def test_failure_propagates(self):
        self.env['STUB_EXIT']='7'
        r=self.run_wrapper('-o',self.d/'out',self.binary); self.assertEqual(r.returncode,7)
    def test_single_script_argument_preserved(self):
        r=self.run_wrapper('-o',self.d/'out','-s','ExportDecompiled.java','-a','name:A::two words',self.binary)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('name:A::two words',self.log.read_text().splitlines())
if __name__=='__main__': unittest.main()
