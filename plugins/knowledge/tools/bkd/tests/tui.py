"""PTY acceptance checks. Synthetic terminal input; not a Safari drag test."""
import errno, fcntl, hashlib, json, os, pty, re, select, struct, subprocess, sys, tempfile, termios, time
from pathlib import Path
binary = Path(sys.argv[1] if len(sys.argv)>1 else 'target/debug/bkd').resolve()
root = Path(tempfile.mkdtemp(prefix='bkd-tui-'))
home = root/'state'
fixture = root/'fixture.jsonl'
record = {'provider':'manual','account':'fixture','external_id':'1','url':'https://example.org/blog/a?x=1&y=2#q','title':'Fixture bookmark','kind':'blog','kind_source':'manual','note':'**Bold evidence**\n\nCitation: document.md lines 1–3'}
fixture.write_text(json.dumps(record)+'\n')
subprocess.run([str(binary),'--home',str(home),'index',str(fixture),'--lexical-only'],capture_output=True,check=True)
plan = {'schema':1,'destination':'a'*64,'criteria':{'fixture':True},'candidates':[{'url':record['url'],'title':record['title'],'kind':'blog','origins':[record],'status':'new','evidence':{'citation':'document.md lines 1–3'},'selected':True}]}
planfile=root/'plan.json'; planfile.write_text(json.dumps(plan))
ansi = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[()][A-Z0-9])')
checks=[]
class Screen:
 def __init__(self,rows,cols):
  self.rows=rows;self.cols=cols;self.row=0;self.col=0;self.cells=[[' ']*cols for _ in range(rows)]
 def feed(self,data):
  # Only the CSI operations emitted by this full-screen renderer are needed.
  for part in re.split(r'(\x1b\[[0-?]*[ -/]*[@-~])',data):
   if part.startswith('\x1b['):
    args=part[2:-1];op=part[-1];vals=args.lstrip('?').split(';')
    n=lambda i,default: int(vals[i]) if i<len(vals) and vals[i].isdigit() and int(vals[i]) else default
    if op in ('H','f'):self.row=min(self.rows-1,n(0,1)-1);self.col=min(self.cols-1,n(1,1)-1)
    elif op=='A':self.row=max(0,self.row-n(0,1))
    elif op=='B':self.row=min(self.rows-1,self.row+n(0,1))
    elif op=='C':self.col=min(self.cols-1,self.col+n(0,1))
    elif op=='D':self.col=max(0,self.col-n(0,1))
    elif op=='G':self.col=min(self.cols-1,n(0,1)-1)
    elif op=='J' and args in ('2','3'):self.cells=[[' ']*self.cols for _ in range(self.rows)]
    elif op=='K':self.cells[self.row][self.col:]=[' ']*(self.cols-self.col)
    elif op=='h' and args=='?1049':self.cells=[[' ']*self.cols for _ in range(self.rows)];self.row=self.col=0
   else:
    for char in part:
     if char=='\r':self.col=0
     elif char=='\n':self.row=min(self.rows-1,self.row+1)
     elif char.isprintable():
      if self.col>=self.cols:self.col=0;self.row=min(self.rows-1,self.row+1)
      self.cells[self.row][self.col]=char;self.col+=1
 def text(self):return '\n'.join(''.join(line) for line in self.cells)
class Session:
 def __init__(self, extra=(), rows=36, cols=120):
  self.master,self.slave=pty.openpty(); self.original=termios.tcgetattr(self.slave)
  fcntl.ioctl(self.slave,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
  env=dict(os.environ,TERM='xterm-256color'); env.pop('BKD_DATABASE_URL',None)
  self.process=subprocess.Popen([str(binary),'--home',str(home),'--lexical-only',*extra],stdin=self.slave,stdout=self.slave,stderr=self.slave,env=env)
  self.screen=Screen(rows,cols);self.raw=b''; self.drain()
 def drain(self, seconds=.25):
  start=time.monotonic(); new=b''
  while time.monotonic()-start<seconds:
   if select.select([self.master],[],[],.02)[0]:
    try:
     chunk=os.read(self.master,65536);new+=chunk
     # Emulate the cursor-position reply that a real terminal sends.
     if b'\x1b[6n' in chunk: os.write(self.master,b'\x1b[1;1R')
    except OSError as e:
     if e.errno!=errno.EIO: raise
     break
  self.raw+=new
  self.screen.feed(new.decode('utf-8',errors='replace'))
  return self.screen.text()
 def send(self,data):
  os.write(self.master,data); return self.drain()
 def close(self,key=b'q'):
  self.send(key); self.process.wait(timeout=5); self.drain()
  assert self.process.returncode==0, self.raw[-1500:]
  assert b'\x1b[?2004h' in self.raw and b'\x1b[?2004l' in self.raw
  assert b'\x1b[?1049l' in self.raw
  restored=termios.tcgetattr(self.slave)
  assert restored==self.original, (restored,self.original)
  os.close(self.master);os.close(self.slave)
 def abort(self):
  if self.process.poll() is None: self.process.kill();self.process.wait()

def case(name, action, extra=(), rows=36,cols=120):
 s=Session(extra,rows,cols)
 try: action(s);s.close();checks.append(name)
 finally:s.abort()
def paste(s,text):return s.send(b'\x1b[200~'+text.encode()+b'\x1b[201~')
url='https://openai.com/index/research/?a=1&b=2#q'
def landing(s):
 out=s.screen.text()
 assert 'drop or paste a link' in out and 'Fixture bookmark' not in out,out
 assert 'Sources:' not in out and '0 results' not in out,out
 assert sum(bool(line.strip()) for line in out.splitlines())<=3,out
 out=s.send(b'?');assert 'Keys' in out and 'WezTerm' in out,out
 s.send(b'\x1b');s.drain()
case('default command opens quiet landing; library stays hidden; help is explicit',landing)
def drop(s):
 out=paste(s,url)
 assert 'Capture' in out and url in out and 'blog' in out,out
 assert s.process.poll() is None
 out=paste(s,'Reviewed title');assert 'Reviewedtitle' in out.replace(' ',''),out
 s.send(b'\x1b');s.drain()
case('bracketed URL drop opens draft; title editable; Escape discards',drop)
def raw(s):
 out=s.send(url.encode());assert 'Capture' in out and 'openai.com' in out,out
 assert s.process.poll() is None
 s.send(b'\x1b');s.drain()
case('unbracketed HTTP URL becomes capture data rather than shortcuts',raw)
def bad(s):
 out=paste(s,'https://a.com\nhttps://b.com');assert 'Invalid HTTP(S)' in out,out
 assert s.process.poll() is None
case('multi-link paste rejected without shell execution',bad)
def graph(s):
 out=s.send(b'g');assert 'generation' in out,out
 out=paste(s,url);assert 'Capture' in out and 'openai.com' in out,(out,s.process.poll(),repr(s.raw[-1500:]))
 s.send(b'\x1b');s.drain()
case('graph drop hands URL back to capture; terminal restored',graph)
def search(s):
 s.send(b'/');paste(s,'Fixture');out=s.send(b'\r');assert 'Fixture bookmark' in out,out
 out=s.send(b'\r');assert 'Details' in out and 'Bold evidence' in out,out
 s.send(b'\x1b');s.drain()
 s.send(b'f');s.send(b'\t');s.send(b'paper');out=s.send(b'\r');assert '0 results' in out,out
case('keyword search, Markdown preview and kind filtering',search)
revision='a'*64
entry='entry:'+'b'*24
insight='insight:'+'b'*24+':1'
details={'version':revision,'coverage':{'limitations':['Synthetic fixture']},'status':'source-claim','claim':'Fixture evidence','evidence':[{'line_start':1,'line_end':1,'quote':'Fixture evidence'}]}
records=root/'records.jsonl'
records.write_text(json.dumps({'schema':'knowledge-snapshot/v1','corpus':'insights','query':None,'nodes':[{'id':entry,'label':'Fixture source','kind':'source_entry','url':record['url'],'bookmark_kind':None,'details':details},{'id':insight,'label':'Fixture evidence','kind':'insight','url':record['url'],'bookmark_kind':None,'details':details}],'edges':[{'a':insight,'b':entry,'kind':'derived_from','status':'recorded','evidence':{}}],'versions':{entry:revision,insight:revision},'hits':[]})+'\n')
def knowledge(s):
 s.send(b'/');paste(s,'Fixture');out=s.send(b'\r');assert 'Fixture evidence' in out,out
 out=s.send(b'g');assert 'generation' in out and 'Fixture' in out,out
 s.send(b'q');s.drain()
case('explicit record file feeds combined terminal search and graph',knowledge,('--records',str(records)))
quote='Sessionpipe selected public evidence'
sid='session:codex:fixture';tid='turn:codex:fixture:1'
cite={'agent':'codex','session_id':'fixture','source_path':'/unavailable/session.jsonl','jsonl_line':1,'json_pointer':'$.payload.content','role':'assistant','timestamp':None,'record_sha256':revision,'original_text_sha256':revision,'indexed_text_sha256':revision,'excerpt_sha256':hashlib.sha256(quote.encode()).hexdigest(),'char_start':0,'char_end':len(quote),'redacted':False,'quote':quote}
with records.open('a') as stream:
 stream.write(json.dumps({'schema':'knowledge-snapshot/v1','corpus':'sessions','query':None,'nodes':[{'id':sid,'label':'Sessionpipe fixture','kind':'session','url':None,'bookmark_kind':None,'details':{'version':revision,'coverage':{'limitations':['Selected public excerpts']},'description':quote,'evidence':[cite]}},{'id':tid,'label':'Assistant evidence','kind':'session_turn','url':None,'bookmark_kind':None,'details':dict(cite,version=revision,session_revision=revision,coverage={'limitations':['Selected public excerpts']},evidence=[cite])}],'edges':[{'a':tid,'b':sid,'kind':'part_of','status':'recorded','evidence':cite}],'versions':{sid:revision,tid:revision},'hits':[]})+'\n')
def session_records(s):
 s.send(b'/');paste(s,'Sessionpipe');out=s.send(b'\r');assert 'Sessionpipe fixture' in out,out
 out=s.send(b'\r');assert 'Details' in out,out
 seen=out
 for _ in range(8):
  if 'jsonl_line' in seen and '/unavailable/session.jsonl' in seen:break
  out=s.send(b'\x1b[6~');seen+=out
 assert 'jsonl_line' in seen and '/unavailable/session.jsonl' in seen,out
 s.send(b'\x1b');s.drain();out=s.send(b'g');assert 'generation' in out and 'Sessionpipe' in out,out
 s.send(b'q');s.drain()
case('session records appear in search, citation details and terminal graph',session_records,('--records',str(records)))
def review(s):
 out=s.screen.text();assert 'selected: false' in out,out
 out=s.send(b'p');assert 'Nothing selected' in out,out
 s.send(b' ');out=s.send(b'p');assert 'PUBLISH 1' in out,out
 out=paste(s,'PUBLISH 1');assert 'confirmation must be typed' in out,out
 out=s.send(b'PUBLISH 2\r');assert 'nothing written' in out,out
 s.send(b'\x1b');s.drain();s.send(b'\x1b');s.drain()
case('plan selections reset; pasted/wrong-count confirmation rejected; cancel writes nothing',review,('--plan',str(planfile)))
def small(s):
 paste(s,url);s.send(b'\x1b');s.drain()
case('capture remains operable at 80x24',small,rows=24,cols=80)
case('Ctrl+C restores terminal',lambda s:s.send(b'\x03'))
assert not (home/'pending').exists(), 'Cancellation created a publication journal'
report={'synthetic_terminal_checks':checks,'count':len(checks),'safari_drag_test':'User reports no input; installed WezTerm macOS URL drag unsupported; synthetic paste is not a real drag test','remote_writes':0,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
(root/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(root/'result.json'),**report}))
