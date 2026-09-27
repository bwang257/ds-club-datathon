"""Build a self-contained HTML labeling tool from a CSV of products.

    .venv/bin/python src/make_label_tool.py labeling/random_250.csv labeling/random_250.html

Input CSV needs Title and category (the label being checked); final_price,
brand, product_url, image_url, and alt ("Other opinion: ...", e.g. a second labeller's
answer) are shown if present. Open the HTML in a browser; progress
is kept in the browser, and Export downloads <name>_labels.csv.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pandas as pd

CATEGORIES = [
    'Audio', 'Bags & Cases', 'Batteries', 'Cables & Charging', 'Cameras & Photography',
    'Car Electronics', 'Computers & Laptops', 'Gaming', 'Keyboards & Mice', 'Marine & GPS',
    'Monitors & Displays', 'Networking', 'Office & School Supplies', 'Optics', 'Other',
    'Phone & Tablet Accessories', 'Phones & Tablets', 'Power Strips & Surge Protectors', 'Printers & Ink',
    'Smart Home & Wearables', 'Storage & Memory Cards', 'TV & Home Entertainment', 'Non-Electronics',
]
KEYS = list('1234567890qwertuiopasdf')  # y = correct, n = note, x = unsure, l = link
assert len(KEYS) == len(CATEGORIES)


def amazon_link(url):
    m = re.search(r'/dp/([A-Z0-9]{10})', unquote(str(url)))
    return f'https://www.amazon.com/dp/{m.group(1)}' if m else ''


def build(csv_path, out_path):
    df = pd.read_csv(csv_path)
    unknown = set(df['category']) - set(CATEGORIES)
    assert not unknown, f'unknown categories: {unknown}'
    items = [{
        'title': r.Title,
        'label': r.category,
        'price': None if pd.isna(r.get('final_price')) else round(float(r.final_price), 2),
        'brand': '' if pd.isna(r.get('brand')) else str(r.brand),
        'link': amazon_link(r.get('product_url', '')),
        'alt': '' if pd.isna(r.get('alt')) else str(r.alt),
        'img': '' if pd.isna(r.get('image_url')) else str(r.image_url).replace('_AC_UL320_', '_AC_UL640_'),
    } for _, r in df.iterrows()]
    name = Path(out_path).stem
    html = TEMPLATE.replace('__DATA__', json.dumps({
        'name': name, 'items': items, 'categories': CATEGORIES, 'keys': KEYS,
    }).replace('</', '<\\/'))
    Path(out_path).write_text(html)
    print(f'wrote {out_path} ({len(items)} items)')


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Category Labeler</title>
<style>
:root { --bg:#fafaf8; --panel:#fff; --ink:#1a1a19; --muted:#6b6a66; --line:#e3e2dd; --accent:#2a78d6;
        --ok:#0c8a3c; --warn:#b26b00; --chip:#eef4fc; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --panel:#1f1f1e; --ink:#f2f2ef; --muted:#a3a29b;
        --line:#34332f; --accent:#5a9cf0; --ok:#3fbf6f; --warn:#e0a23a; --chip:#1d2a3b; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 system-ui, -apple-system, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 20px 16px 40px; }
header { display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
h1 { font-size: 17px; margin: 0; }
.bar { height:6px; background:var(--line); border-radius:3px; margin:12px 0 18px; overflow:hidden; }
.bar > div { height:100%; background:var(--accent); width:0; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:20px; }
.pic { display:block; max-width:100%; max-height:340px; margin:0 auto 12px; border-radius:6px; background:#fff; }
.title { font-size: 20px; font-weight: 600; margin: 4px 0 12px; }
.meta { color:var(--muted); display:flex; gap:16px; flex-wrap:wrap; }
.label { display:inline-block; margin-top:14px; padding:6px 12px; border-radius:6px; background:var(--chip);
         font-weight:600; font-size:16px; }
.status { margin-top:10px; min-height: 22px; font-weight:600; }
.status.correct { color:var(--ok); } .status.changed { color:var(--accent); } .status.unsure { color:var(--warn); }
.note { width:100%; margin-top:10px; padding:8px; font:inherit; border:1px solid var(--line); border-radius:6px;
        background:var(--bg); color:var(--ink); display:none; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(215px, 1fr)); gap:6px; margin-top:16px; }
.opt { border:1px solid var(--line); border-radius:6px; padding:6px 8px; background:var(--panel); color:var(--ink);
       text-align:left; font:inherit; font-size:13px; cursor:pointer; }
.opt:hover { border-color: var(--accent); }
.opt.current { border-color: var(--accent); background: var(--chip); }
kbd { display:inline-block; min-width:20px; padding:0 5px; border:1px solid var(--line); border-bottom-width:2px;
      border-radius:4px; font:12px ui-monospace, monospace; text-align:center; margin-right:6px; }
.help { color:var(--muted); font-size:13px; margin-top:14px; line-height:1.9; }
button.action { font:inherit; padding:6px 12px; border-radius:6px; border:1px solid var(--line);
                background:var(--panel); color:var(--ink); cursor:pointer; }
a { color: var(--accent); }
</style></head><body><main>
<header>
  <h1 id="h"></h1>
  <div style="display:flex; gap:8px">
    <button class="action" id="jump">Next unlabeled</button>
    <button class="action" id="export">Export CSV</button>
  </div>
</header>
<div class="bar"><div id="prog"></div></div>
<div class="card">
  <div class="meta"><span id="pos"></span><span id="price"></span><span id="brand"></span><span id="link"></span></div>
  <div class="title" id="title"></div>
  <img class="pic" id="pic" alt="">
  <div>Current label: <span class="label" id="label"></span></div>
  <div class="meta" id="alt" style="margin-top:8px"></div>
  <div class="status" id="status"></div>
  <input class="note" id="note" placeholder="Note (Enter to save, Esc to cancel)">
</div>
<div class="grid" id="grid"></div>
<div class="help">
  <kbd>Enter</kbd>/<kbd>y</kbd> label is correct &nbsp;·&nbsp; category key = change label &nbsp;·&nbsp;
  <kbd>x</kbd> unsure &nbsp;·&nbsp; <kbd>n</kbd> note &nbsp;·&nbsp; <kbd>l</kbd> open on Amazon &nbsp;·&nbsp;
  <kbd>←</kbd>/<kbd>Backspace</kbd> back &nbsp;·&nbsp; <kbd>→</kbd> skip<br>
  Rules for tricky cases: <code>labeling/guidelines.md</code>. Progress saves in this browser automatically.
</div>
</main>
<script>
const D = __DATA__;
const KEY = 'labeler:' + D.name;
let S = { i: 0, ans: {} };
try { const s = JSON.parse(localStorage.getItem(KEY)); if (s && s.ans) S = s; } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} };
const $ = id => document.getElementById(id);

const grid = $('grid');
D.categories.forEach((c, k) => {
  const b = document.createElement('button');
  b.className = 'opt'; b.dataset.cat = c;
  b.innerHTML = `<kbd>${D.keys[k]}</kbd>${c}`;
  b.onclick = () => choose(c);
  grid.appendChild(b);
});

function render() {
  const it = D.items[S.i], a = S.ans[S.i];
  const done = Object.keys(S.ans).length;
  $('h').textContent = `Category labeler: ${D.name}  (${done}/${D.items.length} done)`;
  $('prog').style.width = (100 * done / D.items.length) + '%';
  $('pos').textContent = `#${S.i + 1} of ${D.items.length}`;
  $('price').textContent = it.price == null ? 'no price' : '$' + it.price;
  $('brand').textContent = it.brand ? 'brand: ' + it.brand : '';
  $('link').innerHTML = it.link ? `<a href="${it.link}" target="_blank" rel="noopener">Amazon ↗</a>` : '';
  $('title').textContent = it.title;
  $('pic').style.display = it.img ? 'block' : 'none'; if (it.img) $('pic').src = it.img;
  const nx = D.items[S.i + 1]; if (nx && nx.img) new Image().src = nx.img;  // preload next
  $('label').textContent = it.label;
  $('alt').textContent = it.alt ? 'Other opinion: ' + it.alt : '';
  const st = $('status');
  st.className = 'status' + (a ? ' ' + a.verdict : '');
  st.textContent = !a ? '' : a.verdict === 'correct' ? '✓ correct'
    : a.verdict === 'changed' ? '→ ' + a.true_category : '? unsure (' + a.true_category + ')';
  if (a && a.note) st.textContent += '  ·  note: ' + a.note;
  grid.querySelectorAll('.opt').forEach(b => b.classList.toggle('current', b.dataset.cat === (a ? a.true_category : it.label)));
  save();
}
function record(verdict, cat) {
  const prev = S.ans[S.i] || {};
  S.ans[S.i] = { verdict, true_category: cat, note: prev.note || '', at: new Date().toISOString() };
}
function next() { if (S.i < D.items.length - 1) S.i++; render(); }
function choose(cat) { record(cat === D.items[S.i].label ? 'correct' : 'changed', cat); next(); }

const note = $('note');
function openNote() { note.style.display = 'block'; note.value = (S.ans[S.i] || {}).note || ''; note.focus(); }
note.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const a = S.ans[S.i] || { verdict: 'unsure', true_category: D.items[S.i].label, at: new Date().toISOString() };
    a.note = note.value.trim(); S.ans[S.i] = a;
    note.style.display = 'none'; render();
  } else if (e.key === 'Escape') { note.style.display = 'none'; }
  e.stopPropagation();
});

document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === 'enter' || k === 'y') { choose(D.items[S.i].label); }
  else if (k === 'x') { record('unsure', (S.ans[S.i] || {}).true_category || D.items[S.i].label); next(); }
  else if (k === 'n') { e.preventDefault(); openNote(); }
  else if (k === 'l') { const u = D.items[S.i].link; if (u) window.open(u, '_blank', 'noopener'); }
  else if (k === 'arrowleft' || k === 'backspace') { e.preventDefault(); if (S.i > 0) S.i--; render(); }
  else if (k === 'arrowright') { next(); }
  else { const j = D.keys.indexOf(k); if (j >= 0) choose(D.categories[j]); }
});

$('jump').onclick = () => {
  const j = D.items.findIndex((_, i) => !S.ans[i]);
  if (j >= 0) { S.i = j; render(); }
};
$('export').onclick = () => {
  const esc = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  const rows = [['Title', 'pipeline_category', 'true_category', 'verdict', 'note', 'labeled_at']];
  D.items.forEach((it, i) => {
    const a = S.ans[i];
    if (a) rows.push([it.title, it.label, a.true_category, a.verdict, a.note, a.at]);
  });
  const blob = new Blob([rows.map(r => r.map(esc).join(',')).join('\n')], { type: 'text/csv' });
  const u = URL.createObjectURL(blob), el = document.createElement('a');
  el.href = u; el.download = D.name + '_labels.csv'; el.click(); URL.revokeObjectURL(u);
};
render();
</script></body></html>
'''

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
