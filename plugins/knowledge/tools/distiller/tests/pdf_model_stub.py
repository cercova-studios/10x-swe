"""Fixture-only OpenRouter server: explicit layout oracle, never a production fallback."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading


class ModelStub:
    def __init__(self):
        self.mode = 'valid'
        self.calls = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert request['model'] == 'deepseek/deepseek-v4.1-flash'
                assert request['provider']['require_parameters'] is True
                assert request['response_format']['json_schema']['strict'] is True
                owner.calls += 1
                content=request['messages'][1]['content']
                assert any(part['type']=='image_url' for part in content)
                data = json.JSONDecoder().raw_decode(content[0]['text'])[0]
                first, last = data['owned_pages']
                spans = [s for s in data['spans'] if first <= s['page'] <= last]
                used = set()
                blocks = []

                def block(kind, selected, joins=None, **kwargs):
                    selected = [s for s in selected if s['id'] not in used]
                    if not selected:
                        return
                    ids = [s['id'] for s in selected]
                    used.update(ids)
                    operations = (joins or ['space']*(len(ids)-1))+['none']
                    blocks.append(dict(kind=kind, parts=[dict(id=id,join=operation) for id,operation in zip(ids,operations)], **kwargs))

                # These expected joins are fixture semantics, not a generalized parser.
                for starts, joins, role, kwargs in [
                    (['W','e have machines now','that we can talk to.'], ['none','space'],'p',{}),
                    (['A printed hyphen: GPT-','3 remains visible.'], ['none'],'p',{}),
                    (['Ev-','ery American institution retains 970 and 52.'], ['dehyphen'],'p',{}),
                    (['Intelligence Ex-','plosion'], ['dehyphen'],'h',{'level':2}),
                    (['An inline callout','1'], ['none'],'p',{}),
                ]:
                    selected = [next((s for s in spans if s['text']==prefix),None) for prefix in starts]
                    if all(selected):
                        block(role, selected, joins, **kwargs)
                for span in spans:
                    if span['id'] in used:
                        continue
                    role = 'h' if span['size'] >= 17 else 'note' if span['size'] < 10 else 'p'
                    kwargs = {'level':2} if role=='h' else {}
                    if span['text']=='1 A retained margin note.':
                        kwargs['reference']=next(s['id'] for s in spans if s['text']=='1')
                    block(role,[span],**kwargs)
                blocks.extend(dict(kind='figure',image=image['id']) for image in data['images'])
                if owner.mode == 'missing' and blocks:
                    blocks.pop(0)
                if owner.mode == 'invented' and blocks:
                    blocks[0]['text'] = 'Invented prose'
                if owner.mode == 'incomplete':
                    done = False
                else:
                    done = True
                body = json.dumps({'model':request['model'],'choices':[{'finish_reason':'stop' if done else 'length','message':{'content':json.dumps({'blocks':blocks})}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def __exit__(self,*args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
