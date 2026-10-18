"""Run via python3 tests/run_native.py; GHIDRA_HOME and JAVA_HOME must be installed."""
import os, pathlib, subprocess, sys, tempfile
root=pathlib.Path(__file__).resolve().parents[1]
work=pathlib.Path(tempfile.mkdtemp(prefix='ghidra-repair-'))
binary=work/'fixture.bin'; binary.write_bytes((bytes.fromhex('c0035fd6')+bytes(12))*64)
args=['bash',str(root/'scripts/ghidra-analyze.sh'),'--project-dir',str(work),'--project-name','fixture','--keep-project','-p','AARCH64:LE:64:v8A','--script-path',str(root/'tests'),'-o',str(work/'out')]
subprocess.run(args+['-s','RepairFixture.java',str(binary)],check=True)
subprocess.run([sys.executable,str(root/'tests/check_exports.py'),str(work/'out')],check=True)
subprocess.run(args+['--reuse','-s','ExportDecompiled.java','-a','addr:00000000',str(binary)],check=True)
assert 'attempted=1' in (work/'out/fixture.bin_decompiled.c').read_text()
subprocess.run(args+['--reuse','-s','ExportDecompiled.java','-a','name:A::same','-a','name:missing',str(binary)],check=True)
assert 'selector=name:missing matches=0' in (work/'out/fixture.bin_decompiled.c').read_text()
subprocess.run(args+['--reuse',str(binary)],check=True)
print('PASS native fixture and read-only reuse:',work)
