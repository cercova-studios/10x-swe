"""Distribution hygiene: source inputs, portable paths and retired surfaces."""
from pathlib import Path
import json
import re
import yaml

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'plugins/knowledge'
errors=[]
for path in (ROOT/'plugins').rglob('*'):
    if not path.is_file() or '__pycache__' in path.parts: continue
    relative=str(path.relative_to(ROOT));raw=path.read_bytes()
    if path.suffix in ('.gguf','.sqlite','.db','.dylib','.so','.exe'):
        errors.append(relative+': runtime artifact in source distribution')
    if raw[:4] in (b'\x7fELF',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf'):
        errors.append(relative+': native executable in source distribution')
    if b'/Users/rohit' in raw:
        errors.append(relative+': machine-specific absolute path')
    if re.search(rb'(ghp_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)',raw):
        errors.append(relative+': possible credential; inspect without logging its value')
for root in (ROOT/'plugins/10x-swe/skills',PACKAGE/'skills'):
    for path in root.glob('*/SKILL.md'):
        text=path.read_text();parts=text.split('---',2)
        assert len(parts)==3,path
        data=yaml.safe_load(parts[1]);assert all(isinstance(data.get(k),str) and data[k].strip() for k in ('name','description')),path
for retired in ('plugins/10x-swe/.envrc','plugins/10x-swe/.mcp.json','plugins/10x-swe/scripts/agent-env.sh'):
    if (ROOT/retired).exists(): errors.append(retired+': retired automatic setup remains')
for path in (ROOT/'plugins/10x-swe').rglob('*.md'):
    if 'AGENT_ROOT' in path.read_text() or 'agent-env.sh' in path.read_text():
        errors.append(str(path.relative_to(ROOT))+': retired path contract remains')
manifest=json.loads((ROOT/'.claude-plugin/marketplace.json').read_text())
assert {p['name'] for p in manifest['plugins']}=={'10x-swe','knowledge'}
assert not errors,'\n'.join(errors)
print('PASS: source-only distribution, no personal paths or detected credential patterns, valid skill metadata, retired ambient setup removed')
