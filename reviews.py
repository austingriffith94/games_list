"""Game reviews: the write-up text format, and the data behind the generated reviews page.

Body format (plain text, as typed in the app's Reviews tab):
* paragraphs are separated by a blank line (single line breaks inside a paragraph are joined with a space)
* a line on its own like  ![caption](file.jpg)  is a figure; add {small} after it for a narrow, in-column figure:
  ![caption](file.jpg){small}.  Files live in the review images folder (REVIEW_IMAGES in app.py).

gather() collects published reviews (or one draft, for the editor's preview) with the game's library details,
and render() fills reviews.template.html with them.  build_reviews.py writes the shareable file.
"""
import base64, io, json, math, os, re
from urllib.parse import quote
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, 'reviews.template.html')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')
COVER_EXTS = ('.jpg', '.jpeg', '.png', '.webp')
WPM = 238                 # reading speed behind the original page's "N min read" (ceil(words / 238) matches all five)
FIG_W, CARD_W = 1600, 720  # embedded figure and card thumbnail widths
FIG = re.compile(r'^!\[(?P<cap>.*)\]\((?P<file>[^()\s]+)\)\s*(?P<small>\{small\})?\s*$')
# outlet, games column, multiplier to 0-100 (same set and order as the dashboard's critic average)
CRITICS = [('Metacritic', 'metacritic', 1), ('PC Gamer', 'pc_gamer', 1), ('GameSpot', 'gamespot', 10), ('IGN', 'ign', 10),
           ('Game Informer', 'game_informer', 10), ('Destructoid', 'destructoid', 10)]
MODES = [('singleplayer', 'Single-player'), ('local_co_op', 'Local co-op'), ('online_co_op', 'Online co-op'),
         ('local_multiplayer', 'Local multiplayer'), ('online_multiplayer', 'Online multiplayer')]


# ----------------------------------------------------------------------------- text format
def slug(title):
    s = re.sub(r"['’]", '', title.lower())
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-') or 'review'


def parse_body(text):
    """Body text -> blocks: {'t': 'p', 'h': text} and {'t': 'fig', 'img': file, 'cap': caption, 'small': bool}."""
    blocks = []
    for chunk in re.split(r'\n\s*\n', (text or '').replace('\r\n', '\n')):
        para = []
        for line in chunk.split('\n'):
            m = FIG.match(line.strip())
            if m:
                if para: blocks.append({'t': 'p', 'h': ' '.join(para)}); para = []
                blocks.append({'t': 'fig', 'img': m['file'], 'cap': m['cap'].strip(), 'small': bool(m['small'])})
            elif line.strip():
                para.append(line.strip())
        if para: blocks.append({'t': 'p', 'h': ' '.join(para)})
    return blocks


def text_stats(blocks):
    """Word count and read time over the paragraphs, plus a card excerpt: opening sentences up to ~70 characters."""
    paras = [b['h'] for b in blocks if b['t'] == 'p']
    words = sum(len(p.split()) for p in paras)
    excerpt = ''
    if paras:
        for sent in re.split(r'(?<=[.!?])\s+', paras[0]):
            excerpt = (excerpt + ' ' + sent).strip()
            if len(excerpt) >= 70: break
    return dict(words=words, mins=max(1, math.ceil(words / WPM)), excerpt=excerpt)


def figure_files(blocks):
    return [b['img'] for b in blocks if b['t'] == 'fig']


def safe_image_name(name):
    """A plain file name for an uploaded image (no folders, only letters, digits, - _ .)."""
    base, ext = os.path.splitext(os.path.basename(name or ''))
    base = re.sub(r'[^A-Za-z0-9_-]+', '_', base).strip('_')[:60] or 'image'
    return base, ext.lower()


# ----------------------------------------------------------------------------- library details for one game
def _cover_path(covers, title):
    base = os.path.join(covers, re.sub(r'[<>:"/\\|?*]', '', title).strip())     # same rule as app.cover_base
    return next((base + e for e in COVER_EXTS if os.path.exists(base + e)), None)


def facts(con, title):
    """What the library knows about a game, for the review's details panel."""
    one = lambda sql, a=(): (lambda r: dict(r) if r else None)(con.execute(sql, a).fetchone())
    g = one('SELECT * FROM games WHERE title=?', (title,))
    rel = [dict(r) for r in con.execute('''SELECT r.system, r.ownership, r.release, r.original_release_date,
              (SELECT round(SUM(hours),2) FROM play_log l WHERE l.game=r.title AND l.system=r.system) AS hours
              FROM releases r WHERE r.title=? ORDER BY r.id''', (title,))]
    span = one('SELECT MIN(date) AS first, MAX(date) AS last, COUNT(DISTINCT date) AS days, round(SUM(hours),2) AS hours FROM play_log WHERE game=?', (title,))
    per_year = dict(con.execute('SELECT substr(date,1,4), round(SUM(hours),2) FROM play_log WHERE game=? GROUP BY 1', (title,)).fetchall())
    years = [[y, per_year.get(str(y), 0)] for y in range(int(span['first'][:4]), int(span['last'][:4]) + 1)] if span['first'] else []
    crit = [dict(n=n, v=g[k]) for n, k, _ in CRITICS if g[k] is not None]
    crit100 = [g[k] * m for _, k, m in CRITICS if g[k] is not None]
    rank = con.execute('SELECT rank FROM top_rank WHERE title=?', (title,)).fetchone()
    dates = [r['original_release_date'] for r in rel if r['original_release_date']]
    return dict(score=g['my_score'], crit=crit, crit_avg=round(sum(crit100) / len(crit100), 1) if crit100 else None,
                zp=g['zero_punctuation'], genre=g['genre'], sub=g['sub_genre'], view=g['camera_view'], style=g['graphic_style'],
                series=g['series'] if (g['series'] or '').lower() != title.lower() else None,
                released=min(dates) if dates else None, modes=[l for k, l in MODES if g[k]],
                systems=[dict(name=r['system'], own=r['ownership'], kind=r['release'], hours=r['hours']) for r in rel],
                hours=span['hours'] or 0, days=span['days'], first=span['first'], last=span['last'],
                plays=g['playthroughs'], avg_play=g['average_playthrough'], goat=bool(g['wikipedia_goat']),
                top=rank[0] if rank and rank[0] <= 10 else None, goty=g['goty_votes'], soundtrack=bool(g['soundtrack_owned']),
                years=years)


# ----------------------------------------------------------------------------- images
def _data_uri(raw, mime):
    return f'data:{mime};base64,' + base64.b64encode(raw).decode()


def _jpeg(im, q):
    buf = io.BytesIO(); im.convert('RGB').save(buf, 'JPEG', quality=q, optimize=True); return buf.getvalue()


def embed_figure(path):
    """Full-width figure as a data URI: small enough JPEGs go in untouched, anything else is resized/re-encoded."""
    raw = open(path, 'rb').read()
    im = Image.open(io.BytesIO(raw))
    if im.format == 'JPEG' and im.width <= FIG_W:
        return _data_uri(raw, 'image/jpeg')
    if im.width > FIG_W: im = im.resize((FIG_W, round(im.height * FIG_W / im.width)), Image.LANCZOS)
    if im.mode in ('RGBA', 'LA', 'P') and 'transparency' in im.info or im.mode in ('RGBA', 'LA'):
        buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True); return _data_uri(buf.getvalue(), 'image/png')
    return _data_uri(_jpeg(im, 85), 'image/jpeg')


def embed_thumb(path, width=CARD_W):
    im = Image.open(path)
    if im.width > width: im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    return _data_uri(_jpeg(im, 78), 'image/jpeg')


def embed_cover(path, w=300, h=450):
    im = Image.open(path).convert('RGB'); want = w / h
    if im.width / im.height > want: cw = int(im.height * want); x = (im.width - cw) // 2; im = im.crop((x, 0, x + cw, im.height))
    else: im = im.crop((0, 0, im.width, int(im.width / want)))           # keep the top of tall art (title lettering)
    return _data_uri(_jpeg(im.resize((w, h), Image.LANCZOS), 80), 'image/jpeg')


# ----------------------------------------------------------------------------- page data
def tiers(con):
    return [dict(r) for r in con.execute('SELECT id, rank, name, description FROM ref_tier ORDER BY rank, id')]


def gather(con, covers, images, drafts=False, only=None, draft=None, embed=True, cover_url=None):
    """Data for reviews.template.html.

    Default: every published review, images embedded (the shareable file).
    only=<review id>: just that review, any status (the editor preview); draft={'tier', 'body'} overrides the
    saved values with the editor's unsaved text.  embed=False links images by URL instead (/review-images/...,
    and cover_url(title) for covers) so the preview builds instantly."""
    T = tiers(con)
    q = 'SELECT r.id, r.title, r.status, r.body, r.updated, g.tier FROM reviews r JOIN games g ON g.title=r.title'
    if only is not None: rows = [dict(r) for r in con.execute(q + ' WHERE r.id=?', (only,))]
    else: rows = [dict(r) for r in con.execute(q + ('' if drafts else " WHERE r.status='published'") + ' ORDER BY r.title COLLATE NOCASE')]
    if draft and rows: rows[0].update({k: v for k, v in draft.items() if k in ('tier', 'body') and v is not None})
    by_tier = {t['name'].lower(): dict(name=t['name'], desc=t['description'], games=[]) for t in T}
    imgs, thumbs, missing = {}, {}, []

    def fig_src(f):
        p = os.path.join(images, f)
        if not os.path.exists(p): missing.append(f); return None
        if f not in imgs: imgs[f] = embed_figure(p) if embed else '/review-images/' + quote(f)
        return imgs[f]

    for r in rows:
        tier = by_tier.get((r['tier'] or '').lower())
        if tier is None: continue                       # no tier yet (a draft) - nothing to file it under
        blocks = [b for b in parse_body(r['body']) if b['t'] == 'p' or fig_src(b['img'])]
        figs = figure_files(blocks)
        card = cover = None
        cp = _cover_path(covers, r['title'])
        if cp: cover = embed_cover(cp) if embed else (cover_url(r['title']) if cover_url else None)
        if figs:
            card = figs[0]
            if card not in thumbs: thumbs[card] = embed_thumb(os.path.join(images, card)) if embed else imgs[card]
        tier['games'].append(dict(id=r['id'], title=r['title'], slug=slug(r['title']), status=r['status'], blocks=blocks,
                                  card=card, cover=cover, updated=r['updated'], facts=facts(con, r['title']), **text_stats(blocks)))
    return dict(tiers=list(by_tier.values()), imgs=imgs, thumbs=thumbs, missing=sorted(set(missing)),
                preview=rows[0]['id'] if only is not None and rows else None)


def render(payload, built=None):
    page = dict(payload, built=built)
    html = open(TEMPLATE, encoding='utf-8').read()
    return html.replace('/*DATA*/', json.dumps(page, separators=(',', ':'), ensure_ascii=False).replace('</', '<\\/'))
