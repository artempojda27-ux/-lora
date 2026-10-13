# -*- coding: utf-8 -*-
"""
TAPULI XML-фід -> data/catalog.js (відділ «Взуття»)

    python3 import_tapuli.py                   # свіжий фід, фото карток локально в img/tp
    python3 import_tapuli.py --feed feed.xml   # з уже завантаженого файлу

Фід віддає лише наявне, тож імпорт — повний перезалив: моделі, яких немає у фіді,
зникають з каталогу, їхні локальні фото видаляються. Перші два фото кожної моделі
(картка + фото при наведенні) зберігаються у WebP на власному хостингу, решта галереї
лишається посиланнями на img.tapuli.shop (сайт тягне їх через оптимізатор Vercel).
Потрібен Pillow.
"""
import argparse, datetime, io, json, os, re, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

FEED = 'https://tapuli.shop/price-xml/?datefrom=2020-01-01&dateto={today}&xml-feed=1&platform=standard'
IMG_DIR = 'img/tp'
LOCAL_PHOTOS = 2
SPEC_KEYS = ('country', 'lining', 'sole', 'insole', 'heel', 'heel_height', 'shaft_height')


def fetch(url, tries=6):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 (ELORA catalog import)'}), timeout=120) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                print(f'  ! {url}: {e}', file=sys.stderr)
                return None
            time.sleep(min(2 ** (i + 1), 30))


def localize(url):
    from PIL import Image, ImageOps
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tools.unify import unify_file
    path = f"{IMG_DIR}/{url.rsplit('/', 1)[-1].rsplit('.', 1)[0]}.webp"
    if os.path.exists(path):
        return path
    raw = fetch(url)
    if not raw:
        return None
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
        im.thumbnail((720, 960))
        im.save(path, 'WEBP', quality=86, method=6)
        unify_file(path)            # єдиний фон ÉLORA (tools/unify.py)
        return path
    except Exception as e:
        print(f'  ! {url}: {e}', file=sys.stderr)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feed', help='локальний XML замість завантаження')
    ap.add_argument('--out', default='data/catalog.js')
    ap.add_argument('--workers', type=int, default=2)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp()
    feed = a.feed
    if not feed:
        raw = fetch(FEED.format(today=datetime.date.today().isoformat()))
        if not raw or b'<catalog' not in raw[:2000]:
            sys.exit('Фід не завантажився — каталог не змінено')
        feed = os.path.join(tmp, 'feed.xml')
        open(feed, 'wb').write(raw)
    norm = os.path.join(tmp, 'catalog.json')
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'normalize.py'), feed, norm], check=True)
    cat = json.load(open(norm, encoding='utf-8'))

    data = []
    for p in cat['products']:
        for v in p['variants']:
            sizes = [s['size'] for s in v['sizes'] if s['available']]
            photos = list(dict.fromkeys([v['photo_main']] + v['photos']))
            if not sizes or not v['price_retail'] or not photos[0]:
                continue
            data.append({
                'id': v['group_id'], 't': v['title'].strip(), 'c': p['category'], 'cs': p['category_slug'],
                'b': p['vendor'] or 'Tapuli', 'p': v['price_retail'],
                'o': v['price_old'] if v['on_sale'] else None,
                'col': v['color'], 'mat': v['material'], 'sz': sizes, 'img': photos[:8],
                'sp': {k: v['specs'][k] for k in SPEC_KEYS if v['specs'].get(k)}, 'g': p['slug'],
            })

    os.makedirs(IMG_DIR, exist_ok=True)
    urls = sorted({u for d in data for u in d['img'][:LOCAL_PHOTOS]})
    with ThreadPoolExecutor(a.workers) as ex:
        local = dict(zip(urls, ex.map(localize, urls)))
    for d in data:
        head = [local.get(u) or u for u in d['img'][:LOCAL_PHOTOS]]
        d['img'] = head + d['img'][LOCAL_PHOTOS:]
    keep = {u for d in data for u in d['img']}
    for f in os.listdir(IMG_DIR):
        if f'{IMG_DIR}/{f}' not in keep:
            os.remove(f'{IMG_DIR}/{f}')

    counts = {}
    for d in data:
        c = counts.setdefault(d['c'], {'name': d['c'], 'slug': d['cs'], 'n': 0})
        c['n'] += 1
    cats = sorted(counts.values(), key=lambda c: -c['n'])
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('/* ÉLORA — каталог, собран из XML-фида TAPULI скриптом import_tapuli.py. */\n')
        f.write('const DATA=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
        f.write('const CATS=' + json.dumps(cats, ensure_ascii=False, separators=(',', ':')) + ';\n')
    lost = sum(1 for v in local.values() if not v)
    print(json.dumps({'models': len(data), 'categories': len(cats), 'photos_local': len(urls) - lost, 'photos_failed': lost},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
