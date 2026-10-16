"""Public message extraction with exact source-record locators; no hidden reasoning."""
import hashlib
import json
from pathlib import Path
from .models import Turn
from .textutil import redact


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def bounded_lines(path, limitations=None):
    with path.open('rb') as stream:
        line = 0
        while raw := stream.readline(16*1024*1024+1):
            line += 1
            if len(raw) > 16*1024*1024:
                while not raw.endswith(b'\n'):
                    raw = stream.readline(16*1024*1024+1)
                    if not raw: break
                if limitations is not None:
                    limitations.append(f'JSONL line {line} omitted: record exceeds 16 MiB')
                continue
            yield line, raw


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get('type') in ('reasoning', 'thinking', 'redacted_thinking'):
            return ''
        return text_content(value.get('content', value.get('text', '')))
    if isinstance(value, list):
        return '\n'.join(text for item in value if (text := text_content(item)))
    return ''


def read_turns(path: Path, agent: str, limitations=None):
    responses, events = [], []
    for line, raw in bounded_lines(path, limitations):
        raw = raw.decode('utf-8')
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # Active writers can leave an unfinished final record; never invent a turn.
            if not raw.endswith('\n'):
                break
            raise ValueError(f'Malformed session record at line {line}')
        if not isinstance(obj, dict):
            continue
        role = text = pointer = None
        bucket = responses
        if agent == 'codex':
            p = obj.get('payload', {})
            if not isinstance(p, dict):
                continue
            if obj.get('type') == 'response_item' and p.get('type') == 'message':
                role = p.get('role')
                if p.get('channel') not in (None, 'final', 'commentary'):
                    continue
                text, pointer = text_content(p.get('content')), '$.payload.content'
            elif obj.get('type') == 'response_item' and p.get('type') in ('function_call_output','custom_tool_call_output'):
                role, text, pointer = 'tool', text_content(p.get('output')), '$.payload.output'
            elif obj.get('type') == 'event_msg' and p.get('type') in ('user_message', 'agent_message'):
                role = 'user' if p['type'] == 'user_message' else 'assistant'
                text, pointer, bucket = text_content(p.get('message')), '$.payload.message', events
        else:
            message = obj.get('message', {})
            if isinstance(message, dict):
                role = message.get('role', obj.get('type'))
                content = message.get('content')
                if role == 'user' and isinstance(content, list) and content and all(isinstance(x, dict) and x.get('type') == 'tool_result' for x in content):
                    role = 'tool'
                text, pointer = text_content(message.get('content')), '$.message.content'
            if not text and obj.get('type') in ('user', 'assistant'):
                role, text, pointer = obj['type'], text_content(obj.get('content')), '$.content'
        if role not in ('user', 'assistant', 'tool') or not text or not text.strip():
            continue
        if len(text.encode()) > 4 * 1024 * 1024:
            if limitations is not None: limitations.append(f'JSONL line {line} omitted: public turn exceeds 4 MiB')
            continue
        clean = redact(text)
        bucket.append(Turn(line, role, clean, obj.get('timestamp'), pointer,
                           sha(raw.rstrip('\r\n')), sha(text), clean != text))
    # Codex duplicates public messages in response/event records. Prefer actual messages.
    turns = responses if responses else events
    return turns


def excerpts(rec, query, limit=3, role=None):
    tokens = [x.lower() for x in query.split() if x]
    scored = []
    for turn in rec.turns:
        if role is not None and turn.role != role:
            continue
        lower = turn.text.lower()
        score = sum(lower.count(t) for t in tokens)
        if score:
            scored.append((score, turn))
    scored.sort(key=lambda x: (-x[0], x[1].line))
    selected = [t for _, t in scored[:limit]]
    out = []
    for t in selected:
        lower = t.text.lower()
        positions = [lower.find(token) for token in tokens if token in lower]
        start = max(0, min(positions, default=0)-100)
        end = min(len(t.text), start+2000)
        quote = t.text[start:end]
        out.append(dict(agent=rec.agent, session_id=rec.native_id, source_path=rec.source_path,
                        jsonl_line=t.line, json_pointer=t.pointer, role=t.role, timestamp=t.timestamp,
                        record_sha256=t.record_sha256, original_text_sha256=t.original_sha256,
                        indexed_text_sha256=sha(t.text), excerpt_sha256=sha(quote),
                        char_start=start, char_end=end, redacted=t.redacted, quote=quote,
                        coverage='Selected public-text excerpt; omitted context and hidden reasoning are not reviewed.' + (f' Export filtered to {role} turns.' if role else '')))
    return out
