"""Reviews page: one self-contained HTML file of every published review.
Usage: python build_reviews.py [out.html] [covers_dir] [review_images_dir]"""
import datetime, os, sys
import reviews
import schema

HERE = os.path.dirname(os.path.abspath(__file__))
_a = [x for x in sys.argv[1:] if not x.startswith('--')]
OUT = _a[0] if _a else 'games_list_reviews.html'
COVERS = _a[1] if len(_a) > 1 else os.path.join(HERE, 'covers')
IMAGES = _a[2] if len(_a) > 2 else os.path.join(HERE, 'review_images')
DB = os.environ.get('GAMELIST_DB', os.path.join(HERE, 'gamelist.db'))

con = schema.connect(DB)
try:
    payload = reviews.gather(con, COVERS, IMAGES)
finally:
    con.close()
html = reviews.render(payload, built=datetime.date.today().isoformat())
open(OUT, 'w', encoding='utf-8').write(html)
n = sum(len(t['games']) for t in payload['tiers'])
print('wrote', OUT, f'{len(html)/1024:.0f} KB, {n} published review{"" if n == 1 else "s"}')
if payload['missing']:
    print('WARNING: missing review images (left out):', ', '.join(payload['missing']))
