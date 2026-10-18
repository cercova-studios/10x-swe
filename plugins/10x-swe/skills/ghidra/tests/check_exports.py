import json, pathlib, sys
p=pathlib.Path(sys.argv[1])
f=json.loads((p/'fixture.bin_functions.json').read_text())
assert isinstance(f,dict), 'canonical function object required'
a=next(x for x in f['functions'] if x['name']=='A::same')
assert len(a['calls'])==55, len(a['calls'])
g=json.loads((p/'fixture.bin_calls.json').read_text())
assert len([x for x in g['callGraph'].values() if x['name'].endswith('::same')])==2
s=json.loads((p/'fixture.bin_symbols.json').read_text())
assert not any(x['address']==a['address'] for x in s['exports']), 'imported provenance is not export'
c=(p/'fixture.bin_decompiled.c').read_text()
assert 'Function: A::same' in c and 'Function: B::same' not in c
assert 'attempted=1' in c and 'cancelled=false' in c
assert f['cancelled'] is False and g['cancelled'] is False
strings=json.loads((p/'fixture.bin_strings.json').read_text())
assert len(strings['strings'][0]['value'])==1500
assert strings['minimumLength']==4 and strings['cancelled'] is False
print('real fixture assertions passed')
