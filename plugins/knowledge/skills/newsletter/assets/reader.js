'use strict';
const editions = JSON.parse(document.getElementById('editions').textContent);
const $ = id => document.getElementById(id);
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
let selected = 0, topic = 'All';
const REFERENCE = /\[([^\]\n]+)\]/g;
// Bracketed source IDs become ascending reference numbers; other bracketed text stays literal.
function resolve(inside, numbers) {
  const found = inside.split(/[;,]/).map(id => numbers[id.trim()]);
  return found.every(Boolean) ? [...new Set(found)].sort((a, b) => a - b) : null;
}
function references(refs) {
  const span = el('span', 'source-ref');
  span.append('[');
  refs.forEach((number, i) => {
    const link = el('a', '', String(number));
    link.href = `#source-${number}`;
    link.setAttribute('aria-label', `Source ${number}`);
    link.onclick = () => { $('evidence').open = true; };
    if (i) span.append('; ');
    span.append(link);
  });
  span.append(']');
  return span;
}
function paragraphs(parent, text, cls) {
  const numbers = editions[selected]?.reading.numbers || {};
  for (const part of text.split(/\n\s*\n/)) {
    const p = el('p', cls);
    let last = 0;
    for (const match of part.matchAll(REFERENCE)) {
      const refs = resolve(match[1], numbers);
      if (!refs) continue;
      p.append(part.slice(last, match.index), references(refs));
      last = match.index + match[0].length;
    }
    p.append(part.slice(last));
    parent.append(p);
  }
}
function sourceLinks(story, view, fields) {
  const inline = new Set(fields.flatMap(field => [...story[field].matchAll(REFERENCE)]
    .flatMap(match => resolve(match[1], view.numbers) || [])));
  const missing = [...new Set(story.citations.map(c => view.numbers[c.source_id]))]
    .filter(number => !inline.has(number)).sort((a, b) => a - b);
  if (!missing.length) return null;
  const row = el('div', 'source-links', 'Sources: ');
  row.append(references(missing));
  return row;
}
function storyArticle(story, view, background) {
  const article = el('article', 'story' + (story.kind === 'deep_dive' ? ' lead' : ' brief'));
  article.id = story.id;
  article.tabIndex = -1;
  const meta = el('div', 'story-meta');
  meta.append(el('span', '', story.topic), el('span', '', background ? 'Background' : story.event_date),
              el('span', '', story.kind === 'deep_dive' ? 'Deep dive' : 'Brief'));
  article.append(meta, el('h3', '', story.headline));
  paragraphs(article, story.summary);
  const sections = [['Under the hood', 'technical_detail'], ['Why it matters', 'why_it_matters'],
                    ['For your work', 'relevance'], ['Limits & unknowns', 'limitations']];
  if (story.kind === 'deep_dive') {
    for (const [heading, field] of sections) {
      article.append(el('h4', '', heading));
      paragraphs(article, story[field], 'technical');
    }
  } else if (story.limitations) {
    paragraphs(article, story.limitations, 'qualification');
  }
  const shown = story.kind === 'deep_dive' ? ['summary', ...sections.map(([, field]) => field)] : ['summary', 'limitations'];
  const fallback = sourceLinks(story, view, shown);
  if (fallback) article.append(fallback);
  return article;
}
function evidenceNotes(edition) {
  const details = el('details'); details.id = 'evidence';
  details.append(el('summary', '', 'Sources & evidence'));
  const list = el('ol', 'citations');
  for (const source of edition.reading.references) {
    const row = el('li'); row.id = `source-${source.number}`;
    const link = el('a', '', source.title); link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    row.append(link, el('div', 'source-coverage', `${source.published_at || 'Date unconfirmed'} · ${source.coverage}`));
    const origins = [];
    if (source.original_url) origins.push(['Original source', source.original_url]);
    for (const p of source.provenance || []) {
      origins.push([`${p.provider} catalog`, p.catalog_url], [`${p.provider} evidence`, p.evidence_url]);
    }
    for (const [label, url] of origins) {
      const origin = el('a', 'source-coverage', label); origin.href = url; origin.target = '_blank'; origin.rel = 'noopener noreferrer';
      const line = el('div'); line.append(origin); row.append(line);
    }
    const quotes = source.preview_quotes;
    const passages = el('details'); passages.append(el('summary', '', 'Supporting excerpt'));
    for (const quote of quotes) {
      passages.append(el('blockquote', '', quote));
      for (const p of source.provenance || []) for (const segment of p.segments || []) {
        if (!segment.text.includes(quote)) continue;
        const seconds = Math.floor(segment.startMs / 1000);
        const link = el('a', '', `Recording at ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`); link.href = segment.citation_url;
        passages.append(link);
      }
    }
    if (quotes.length) row.append(passages);
    list.append(row);
  }
  details.append(list); return details;
}
function coverageTable(edition) {
  const table = el('table', 'coverage-table'); table.append(el('caption', '', 'Coverage by topic'));
  const header = el('tr');
  for (const label of ['Topic', 'Search', 'Sources', 'Stories']) { const cell = el('th', '', label); cell.scope = 'col'; header.append(cell); }
  const head = el('thead'); head.append(header); table.append(head); const body = el('tbody');
  for (const name of edition.research.topics) {
    const row = el('tr'), label = el('th', '', name); label.scope = 'row'; row.append(label);
    const providers = [...new Set([
      ...(edition.research.coverage || []).filter(c => c.topic === name).map(c => c.provider),
      ...edition.research.sources.filter(s => (s.topics || []).includes(name)).flatMap(s => (s.provenance || []).map(p => p.provider))
    ])];
    const sources = edition.research.sources.filter(s => (s.topics || []).includes(name)).length;
    const stories = edition.issue.stories.filter(s => s.topic === name).length;
    for (const value of [providers.join(', ') || 'Not recorded', String(sources), stories ? String(stories) : 'No story published']) row.append(el('td', '', value));
    body.append(row);
  }
  table.append(body); $('coverage').append(table);
}
function jump(story) {
  topic = 'All'; $('search').value = ''; display();
  const article = $(story.id); article.scrollIntoView(); article.focus({preventScroll: true});
}
function display() {
  const edition = editions[selected]; $('archive').replaceChildren();
  editions.forEach((item, i) => {
    const button = el('button', '', item.date); button.setAttribute('aria-pressed', String(i === selected));
    button.onclick = () => { selected = i; topic = 'All'; $('search').value = ''; display(); document.querySelector('.archive-menu').open = false; };
    $('archive').append(button);
  });
  for (const id of ['intro', 'stories', 'topics', 'coverage', 'source-notes']) $(id).replaceChildren();
  if (!edition) {
    $('dateline').textContent = 'Your reading room';
    $('intro').append(el('h1', '', 'A little quiet. A little clarity.'), el('p', 'standfirst', 'Your next edition will appear here after its research and editorial checks pass.'));
    $('markdown').hidden = true; return;
  }
  $('markdown').hidden = false; $('markdown').href = edition.markdown;
  $('dateline').textContent = new Date(edition.date + 'T12:00:00').toLocaleDateString('en-US', {weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'});
  const issue = edition.issue, view = edition.reading;
  $('intro').append(el('h1', '', issue.title)); paragraphs($('intro'), issue.standfirst, 'standfirst');
  $('intro').append(el('p', 'issue-counts', `${view.current.length} current stories · ${view.background.length} background reads · ${issue.stories.filter(s => s.kind === 'deep_dive').length} deep dives`));
  const briefing = el('section', 'briefing'); briefing.setAttribute('aria-label', 'Quick briefing');
  briefing.append(el('h2', '', view.current.length ? 'Today in 60 seconds' : 'Reading shortlist'));
  const list = el('ol');
  for (const story of (view.current.length ? view.current : view.background).slice(0, 6)) {
    const row = el('li'), link = el('a', '', story.headline); link.href = `#${story.id}`;
    link.onclick = event => { event.preventDefault(); jump(story); };
    row.append(link); list.append(row);
  }
  briefing.append(list); $('intro').append(briefing);
  const editorial = el('section', 'editorial'); editorial.append(el('h2', '', 'The thread')); paragraphs(editorial, issue.editorial); $('intro').append(editorial);
  for (const name of ['All', ...edition.research.topics]) {
    const option = el('option', '', name); option.value = name; option.selected = topic === name; $('topics').append(option);
  }
  const query = $('search').value.trim().toLowerCase();
  const matches = story => (topic === 'All' || story.topic === topic) && (!query || [story.headline, story.summary, story.technical_detail, story.topic].join(' ').toLowerCase().includes(query));
  const groups = [['Current news', view.current, false], ['Background analysis', view.background.filter(s => s.kind === 'deep_dive'), true],
                  ['Also worth reading', view.background.filter(s => s.kind === 'brief'), true]];
  let count = 0;
  for (const [title, stories, background] of groups) {
    const visible = stories.filter(matches); if (!visible.length) continue;
    const section = el('section', background ? 'background' : 'current-news'); section.append(el('h2', 'section-heading', title));
    if (background) section.append(el('p', 'section-note', 'Earlier or undated material, separate from current news.'));
    for (const story of visible) section.append(storyArticle(story, view, background));
    $('stories').append(section); count += visible.length;
  }
  $('result-count').textContent = `${count} stories shown`;
  if (!count) $('stories').append(el('p', 'empty', 'No stories match. Try another topic or search.'));
  $('source-notes').append(evidenceNotes(edition));
  const research = edition.research;
  paragraphs($('coverage'), `Research window: ${research.window_start} — ${research.window_end}. ${research.sources.length} retained sources. ${research.limits.original_pages} original HTML pages extracted. Search excerpts do not imply full-document review.`);
  for (const note of research.coverage_notes || []) paragraphs($('coverage'), note);
  coverageTable(edition);
}
$('search').addEventListener('input', display);
$('topics').addEventListener('change', () => { topic = $('topics').value; display(); });
document.addEventListener('keydown', event => {
  if (event.key === '/' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) { event.preventDefault(); $('search').focus(); }
  if (event.key === 'Escape') { $('search').value = ''; display(); }
});
$('theme').onclick = () => { document.body.classList.toggle('dark'); try { localStorage.setItem('fieldnotes-theme', document.body.classList.contains('dark') ? 'dark' : 'light'); } catch {} };
try { if (localStorage.getItem('fieldnotes-theme') === 'dark') document.body.classList.add('dark'); } catch {}
display();
