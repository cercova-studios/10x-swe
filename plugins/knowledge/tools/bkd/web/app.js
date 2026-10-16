'use strict';
const $ = id => document.getElementById(id);
const status = text => { $('status').textContent = text; };
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function node(tag, text = '') { const el = document.createElement(tag); el.textContent = text; return el; }
function safeLink(text) {
  if (typeof text !== 'string' || text.length > 8192 || /[\s\x00-\x1f\x7f]/.test(text)) return null;
  try { const u = new URL(text); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? text : null; } catch { return null; }
}
function markdown(text) {
  // Only the existing inert server Markdown renderer supplies this HTML.
  const root = node('div'); root.innerHTML = text || ''; return root;
}
function parameters() {
  const p = new URLSearchParams();
  if ($('kind').value) p.set('kind', $('kind').value);
  if ($('source').value) p.set('source', $('source').value);
  if ($('knowledge').checked) p.set('knowledge', '1');
  return p;
}
function evidence(root, details) {
  if (!details) return;
  if (details.inspection) root.append(node('p', details.inspection));
  for (const entry of details.inspected_sources || []) { root.append(node('h3', entry.label)); evidence(root, entry.details); }
  if (details.coverage) root.append(node('h3', 'Recorded inspection coverage'), node('pre', JSON.stringify(details.coverage, null, 2)));
  if (details.evidence) root.append(node('h3', 'Citations'), node('pre', JSON.stringify(details.evidence, null, 2)));
  for (const key of ['caveats', 'integrity', 'note', 'description', 'authority']) if (details[key]) root.append(node('p', details[key]));
  if (details.open_with) root.append(node('h3', 'Open in companion tool'), node('pre', details.open_with.map(arg => "'" + arg.replaceAll("'", "'\\''") + "'").join(' ')));
  for (const insight of details.insights || []) { root.append(node('h3', insight.claim)); evidence(root, insight); }
}
function explore(id) {
  const b = node('button', 'Explore relationships'); b.type = 'button';
  b.onclick = () => { $('quicklook').close(); openGraph(id); }; return b;
}
let rows = [], selected = -1, offset = 0, total = 0, listingVersion = 0;
const kinds = { blog: 'Blog', article: 'Article', paper: 'Paper', video: 'Video', documentation: 'Docs', book: 'Book', other: 'Other', insights: 'Insight', skills: 'Skill', sessions: 'Session' };
function selectRow(index, focus = false) {
  selected = index;
  [...document.querySelectorAll('.file-list tbody tr')].forEach((tr, i) => {
    tr.classList.toggle('selected', i === index);
    tr.querySelector('button').setAttribute('aria-pressed', String(i === index));
    if (focus && i === index) tr.querySelector('button').focus();
  });
  $('peek').disabled = selected < 0;
}
function renderRows() {
  $('results').replaceChildren(); $('empty').hidden = rows.length > 0;
  $('peek').disabled = !rows.length;
  if (rows.length) {
    const table = node('table'); table.className = 'file-list';
    const head = node('thead'), heading = node('tr');
    for (const text of ['Name', 'Kind', 'Source']) { const th = node('th', text); th.scope = 'col'; heading.append(th); }
    head.append(heading); const body = node('tbody');
    rows.forEach((r, i) => {
      const tr = node('tr'); if (r.group) tr.dataset.kind = r.group;
      const cell = node('td'), b = node('button'); b.type = 'button'; b.dataset.id = r.id;
      b.append(Object.assign(node('span', r.kind === 'video' ? '▷' : '▤'), { className: 'file-icon' }));
      b.append(Object.assign(node('span', r.title || r.url || 'Untitled'), { className: 'file-name' }));
      const domain = safeLink(r.url) ? new URL(r.url).hostname : r.id;
      b.append(Object.assign(node('span', domain), { className: 'file-domain' }));
      b.onclick = () => selectRow(i); b.ondblclick = () => quickLook(r);
      b.onkeydown = e => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); selectRow(Math.max(0, Math.min(rows.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1))), true); }
        if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); selectRow(i); quickLook(r); }
      };
      if (safeLink(r.url)) {
        tr.draggable = true;
        tr.ondragstart = e => { e.dataTransfer.setData('text/uri-list', r.url); e.dataTransfer.setData('text/plain', r.url); e.dataTransfer.effectAllowed = 'copy'; };
      }
      cell.append(b); tr.append(cell, node('td', kinds[r.kind] || r.kind), node('td', (r.sources || []).join(', ') || r.group || '')); body.append(tr);
    });
    table.append(head, body); $('results').append(table);
  }
  selectRow(rows.length ? 0 : -1);
  $('back').disabled = offset === 0 || Boolean($('query').value.trim());
  $('forward').disabled = offset + rows.length >= total || Boolean($('query').value.trim());
  $('pagecount').textContent = total ? `${offset + 1}–${offset + rows.length} / ${total}` : '';
}
async function listing() {
  const version = ++listingVersion, params = parameters(), query = $('query').value.trim();
  $('map').hidden = true; $('results').hidden = false;
  $('location').textContent = query ? 'Search results' : $('source').selectedOptions[0].text;
  if (query) params.set('q', query); else params.set('offset', offset);
  status(query ? 'Searching locally…' : '');
  try {
    const data = await api((query ? '/api/search?' : '/api/bookmarks?') + params);
    if (version !== listingVersion) return;
    rows = [...data.results]; total = data.total;
    for (const key of ['insights', 'skills', 'sessions']) for (const hit of data[key] || []) rows.push({ id: hit.node.id, title: hit.node.label, url: hit.node.url, kind: key, group: key, details: hit.node.details });
    renderRows(); status(`${data.results.length} bookmarks${query && $('knowledge').checked ? ' · separate corpus ranks' : ''}`);
  } catch (e) { if (version === listingVersion) { rows = []; total = 0; renderRows(); status(e.message); } }
}
$('search').onsubmit = e => { e.preventDefault(); offset = 0; listing(); };
$('query').oninput = () => { if (!$('query').value) { offset = 0; listing(); } };
for (const id of ['source', 'kind', 'knowledge']) $(id).onchange = () => { offset = 0; listing(); };
$('back').onclick = () => { offset = Math.max(0, offset - 100); listing(); };
$('forward').onclick = () => { offset += 100; listing(); };
function capture(url = '') {
  if ($('publish').disabled) { $('capturestatus').textContent = 'Waiting for the current publication receipt.'; return false; }
  $('url').value = url; $('title').value = ''; $('savekind').value = ''; $('confirm').checked = false; $('capturestatus').textContent = '';
  if (!$('capture').open) $('capture').showModal();
  $(url ? 'title' : 'url').focus();
  return true;
}
$('add').onclick = () => capture();
$('capture').addEventListener('cancel', e => { if ($('publish').disabled) { e.preventDefault(); $('capturestatus').textContent = 'Waiting for receipts; an in-flight publication cannot be cancelled by closing this window.'; } });
for (const b of document.querySelectorAll('[data-close]')) b.onclick = () => $(b.dataset.close).close();
for (const id of ['url', 'title', 'savekind']) $(id).addEventListener('input', () => { $('confirm').checked = false; });
$('save').onsubmit = async e => {
  e.preventDefault(); const fields = [...$('save').elements];
  const payload = { url: $('url').value, title: $('title').value, kind: $('savekind').value, confirm_public: $('confirm').checked };
  if (!safeLink(payload.url)) { $('capturestatus').textContent = 'Enter one HTTP(S) URL without credentials.'; return; }
  fields.forEach(el => { el.disabled = true; }); $('capturestatus').textContent = 'Publishing reviewed bookmark…';
  try {
    const data = await api('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    $('capturestatus').textContent = data.status === 'already_saved' ? 'Already saved; existing public title preserved.' : 'Published. Run bkd sync --source neon to refresh the local library.';
  } catch (error) { $('capturestatus').textContent = error.message; }
  finally { fields.forEach(el => { el.disabled = false; }); $('confirm').checked = false; }
};
const drop = $('drop'); let dragDepth = 0;
document.addEventListener('dragover', e => { e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'; });
document.addEventListener('dragenter', e => { e.preventDefault(); dragDepth++; drop.classList.add('drag'); });
document.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; drop.classList.remove('drag'); } });
document.addEventListener('drop', e => {
  e.preventDefault(); dragDepth = 0; drop.classList.remove('drag');
  const values = (e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain')).split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith('#'));
  if (values.length === 1 && safeLink(values[0])) {
    // Browsers normalize URI-list root URLs; preserve equivalent plain text for exact bookmark identity.
    const plain = safeLink(e.dataTransfer.getData('text/plain').trim());
    const url = plain && new URL(plain).href === new URL(values[0]).href ? plain : values[0];
    if (capture(url)) status('Link captured for review. Nothing published.');
  }
  else status('Drop exactly one HTTP(S) link. Files and commands are not opened.');
});
document.addEventListener('paste', e => {
  if (e.target.closest('input,textarea,[contenteditable]') || $('capture').open || $('quicklook').open) return;
  const url = e.clipboardData.getData('text/plain').trim();
  if (safeLink(url)) { e.preventDefault(); capture(url); }
});
let previewVersion = 0, previewRow = null, readerRequest = null, previewMode = 'web';
function previewModeSet(mode) {
  previewMode = mode;
  $('webpreview').hidden = mode !== 'web'; $('reader').hidden = mode !== 'reader'; $('notes').hidden = mode !== 'notes';
  for (const [id, value] of [['webmode', 'web'], ['readermode', 'reader'], ['notesmode', 'notes']]) $(id).setAttribute('aria-pressed', String(mode === value));
}
function quickLook(r) {
  readerRequest?.abort(); previewVersion++; previewRow = r;
  $('previewtitle').textContent = r.title || r.url || 'Untitled';
  const url = safeLink(r.url); $('original').hidden = !url;
  if (url) $('original').href = url; else $('original').removeAttribute('href');
  $('webmode').disabled = $('readermode').disabled = !url;
  $('reader').replaceChildren(); $('notes').replaceChildren(markdown(r.excerpt_html)); evidence($('notes'), r.details); $('notes').append(explore(r.id));
  if (r.graph_path) $('notes').append(node('h3', 'Graph support'), node('pre', JSON.stringify(r.graph_path, null, 2)));
  if (r.passage) $('notes').append(node('h3', 'Matched passage'), node('pre', JSON.stringify(r.passage, null, 2)));
  $('previewstatus').textContent = 'Sites may block embedding. Use Reader or Open original if the frame is blank.';
  if (url && !r.group) $('webpreview').src = url; else $('webpreview').removeAttribute('src');
  previewModeSet(url && !r.group ? 'web' : 'notes'); $('quicklook').showModal();
}
$('peek').onclick = () => { if (rows[selected]) quickLook(rows[selected]); };
$('quicklook').addEventListener('close', () => { readerRequest?.abort(); previewVersion++; $('webpreview').removeAttribute('src'); });
$('webmode').onclick = () => { readerRequest?.abort(); if (safeLink(previewRow.url)) $('webpreview').src = previewRow.url; previewModeSet('web'); $('previewstatus').textContent = 'Sites may block embedding. Use Reader or Open original if the frame is blank.'; };
$('notesmode').onclick = () => { readerRequest?.abort(); previewModeSet('notes'); $('previewstatus').textContent = 'Saved notes and recorded evidence'; };
function readerText(html) {
  // Template contents are inert. Never insert fetched nodes, scripts, links or resources into the live document.
  const template = document.createElement('template'); template.innerHTML = html;
  const title = template.content.querySelector('title')?.textContent.trim().slice(0, 500);
  template.content.querySelectorAll('script,style,noscript,iframe,object,embed,img,svg,form,nav,header,footer,aside,button,input,select,textarea,link,meta,base,[hidden],[aria-hidden="true"]').forEach(el => el.remove());
  template.content.querySelectorAll('br').forEach(el => el.replaceWith(document.createTextNode('\n')));
  const candidates = [...template.content.querySelectorAll('article,main,[role="main"]')].slice(0, 200);
  const root = candidates.sort((a, b) => b.textContent.length - a.textContent.length)[0] || template.content;
  const result = document.createDocumentFragment(); let size = 0;
  for (const el of root.querySelectorAll('h1,h2,h3,h4,h5,h6,p,pre,blockquote,li')) {
    if (el.parentElement?.closest('p,pre,blockquote,li')) continue;
    const text = el.textContent.trim(); if (!text) continue;
    size += text.length; if (size > 200000) throw new Error('Article text exceeds the reader limit. Open the original.');
    result.append(node(el.tagName === 'LI' ? 'p' : el.tagName.toLowerCase(), el.tagName === 'LI' ? '• ' + text : text));
  }
  if (size < 80) throw new Error('No readable article text found. The page may require JavaScript or sign-in; open the original.');
  return { title, body: result };
}
$('readermode').onclick = async () => {
  const version = ++previewVersion, row = previewRow; readerRequest?.abort(); readerRequest = new AbortController();
  previewModeSet('reader'); $('previewstatus').textContent = 'Converting public HTML to text…';
  try {
    const data = await api('/api/reader', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: row.url }), signal: readerRequest.signal });
    if (version !== previewVersion || previewMode !== 'reader') return;
    const article = readerText(data.html); $('reader').replaceChildren(node('h1', article.title || row.title || new URL(data.url).hostname), article.body);
    $('previewstatus').textContent = 'Text reader · scripts, images and navigation removed · not saved to your bookmarks';
  } catch (error) { if (error.name !== 'AbortError' && version === previewVersion && previewMode === 'reader') $('previewstatus').textContent = error.message; }
};
document.addEventListener('keydown', e => {
  if (e.key === ' ' && !e.target.closest('input,textarea,select,button') && !$('capture').open && !$('quicklook').open && rows[selected]) { e.preventDefault(); quickLook(rows[selected]); }
});
let graph=null,page=0,pageSize=80;const canvas=document.querySelector('canvas');
function draw(){
  if(!graph)return;
  canvas.width=Math.max(260,Math.floor(canvas.clientWidth));
  const columns=Math.max(1,Math.min(8,Math.floor(canvas.width/135)));
  pageSize=columns*10;
  page=Math.min(page,Math.max(0,Math.ceil(graph.nodes.length/pageSize)-1));
  const nodes=graph.nodes.slice(page*pageSize,(page+1)*pageSize);
  canvas.height=Math.max(180,Math.ceil(nodes.length/columns)*70+40);
  const points=new Map(),ctx=canvas.getContext('2d');
  nodes.forEach((n,i)=>points.set(n.id,[50+(i%columns)*(canvas.width/columns),40+Math.floor(i/columns)*70]));
  for(const e of graph.edges){
    if(!points.has(e.a)||!points.has(e.b))continue;
    const [x,y]=points.get(e.a),[a,b]=points.get(e.b);
    ctx.strokeStyle=e.status==='inferred'?'#577163':'#8ab6a3';
    ctx.setLineDash(e.status==='inferred'?[3,5]:[]);
    ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(a,b);ctx.stroke();
  }
  ctx.setLineDash([]);$('nodes').replaceChildren();
  const describe=n=>{
    const edges=graph.edges.filter(e=>e.a===n.id||e.b===n.id);
    status(n.label+' · '+(n.bookmark_kind||n.kind));
    let details=$('graphdetails');
    if(!details){details=node('section','');details.id='graphdetails';details.setAttribute('aria-label','Selected entity and relationships');$('map').append(details);}
    details.replaceChildren(node('h2',n.label),node('p',n.id));evidence(details,n.details);
    for(const e of edges){const id=e.a===n.id?e.b:e.a;const target=graph.nodes.find(n=>n.id===id);const b=node('button',`${e.kind} (${e.status}) → ${target?.label||id}`);b.type='button';b.onclick=()=>focusNode(id);details.append(b,node('pre',JSON.stringify(e.evidence,null,2)));}
    if(graph.knowledge?.stale_links?.length)details.append(node('p',`${graph.knowledge.stale_links.length} reviewed links are stale and excluded.`));
    details.dataset.nodeId=n.id;
  };
  for(const n of nodes){
    const [x,y]=points.get(n.id);
    ctx.fillStyle=n.kind==='bookmark'?'#b7e6d3':'#deb68a';
    ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();
    ctx.font='12px system-ui';ctx.fillText(n.label.slice(0,18),x-30,y+18);
    const button=node('button',`[${n.bookmark_kind||n.kind}] ${n.label}`);
    button.type='button';button.onclick=()=>describe(n);
    const li=node('li','');li.append(button);$('nodes').append(li);
  }
  canvas.onclick=event=>{
    const bounds=canvas.getBoundingClientRect(),x=event.clientX-bounds.left,y=event.clientY-bounds.top;
    const nearest=nodes.find(n=>{const [a,b]=points.get(n.id);return Math.hypot(a-x,b-y)<25;});
    if(nearest)describe(nearest);
  };
  $('graphstatus').textContent=`Page ${page+1}/${Math.max(1,Math.ceil(graph.nodes.length/pageSize))} · ${graph.nodes.length} nodes · ${graph.edges.length} edges. Dotted edges are inferred. Cross-page paths: bkd path / related.`;
  if(focusId){const selected=graph.nodes.find(n=>n.id===focusId);if(selected)describe(selected);focusId=null;}
}
let focusId=null;
function focusNode(id){const index=graph.nodes.findIndex(n=>n.id===id);if(index<0)return;page=Math.floor(index/pageSize);focusId=id;draw();$('graphdetails')?.scrollIntoView({block:'nearest'});}
async function openGraph(id){try{listingVersion++;graph=await api('/api/graph?'+parameters());page=0;$('results').hidden=true;$('empty').hidden=true;$('graphdetails')?.remove();$('map').hidden=false;draw();if(id)focusNode(id);}catch(e){status(e.message);}}
$('graph').onclick=()=>openGraph();
$('prev').onclick=()=>{page=Math.max(0,page-1);draw();};
$('next').onclick=()=>{page=Math.min(Math.max(0,Math.ceil(graph.nodes.length/pageSize)-1),page+1);draw();};
function resize(){ $('source').size = window.matchMedia('(max-width:700px)').matches ? 1 : 5; draw(); }
window.addEventListener('resize',resize); resize();
api('/api/status').then(async data=>{$('knowledge').checked=data.knowledge_default;await listing();if(data.pending_batches)status(`${data.pending_batches} uncertain save batches; inspect bkd doctor before retrying`);}).catch(e=>status(e.message));
