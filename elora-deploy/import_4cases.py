# -*- coding: utf-8 -*-
"""
4cases.com.ua -> data/4cases.js
Шкіряна галантерея (сумки, гаманці, ремені…) для відділу «Сумки та аксесуари».

    python3 import_4cases.py                 # ціни як на сайті (оптові)
    python3 import_4cases.py --markup 1.6    # роздрібна націнка, округлення до 10 ₴
    python3 import_4cases.py --images-only   # лише докачати фото для наявного data/4cases.js

Сайт на OkayCMS. Категорія: /catalog/<slug>/page-N, у картці списку є назва,
фото, ціна (data-price) і залишок (data-stock). Зі сторінки товару беремо
галерею, характеристики та опис. Беремо лише те, що в наявності (stock > 0);
розділи «бувші в продажу» та «некондиція» пропускаємо.
Фото зберігаються локально в img/4c/*.webp (сервер 4cases рве з'єднання, коли
браузер тягне десятки фото одночасно, тож хотлінк ненадійний). Для фото потрібен Pillow.
"""
import argparse, hashlib, html, io, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

BASE = 'https://4cases.com.ua'
# порядок = порядок на вітрині
CATS = [
    ('zhenskie-sumki',         'Жіночі сумки'),
    ('klatchi-ta-kosmetichki', 'Клатчі та косметички'),
    ('zhenskie-koshelki',      'Жіночі гаманці'),
    ('muzhskie-sumki',         'Чоловічі сумки'),
    ('portfeli',               'Портфелі'),
    ('ryukzaki',               'Рюкзаки'),
    ('muzhskie-portmone',      'Портмоне'),
    ('vizitnitsy2',            'Візитниці'),
    ('vizitnitsy',             'Візитниці'),
    ('remni',                  'Ремені'),
    ('sharfy',                 'Шарфи'),
]
# колір з характеристик (укр/рос) -> назва зі шкали вітрини
COLOR_RULES = [
    ('черн', 'Чорний'), ('чорн', 'Чорний'), ('black', 'Чорний'),
    ('коньяк', 'Рудий'), ('рыж', 'Рудий'), ('руд', 'Рудий'), ('cognac', 'Рудий'),
    ('коричн', 'Коричневий'), ('кофе', 'Коричневий'), ('шоколад', 'Коричневий'), ('brown', 'Коричневий'), ('coffee', 'Коричневий'),
    ('бордо', 'Бордовий'), ('вишн', 'Бордовий'), ('марсал', 'Бордовий'),
    ('беж', 'Бежевий'), ('капучин', 'Бежевий'), ('песоч', 'Бежевий'), ('пісоч', 'Бежевий'), ('карамел', 'Бежевий'),
    ('молоч', 'Білий'), ('бел', 'Білий'), ('біл', 'Білий'), ('white', 'Білий'),
    ('красн', 'Червоний'), ('червон', 'Червоний'), ('red', 'Червоний'),
    ('пудр', 'Пудровий'), ('розов', 'Рожевий'), ('рожев', 'Рожевий'), ('pink', 'Рожевий'),
    ('голуб', 'Блакитний'), ('блакит', 'Блакитний'),
    ('син', 'Синій'), ('blue', 'Синій'),
    ('зел', 'Зелений'), ('олив', 'Зелений'), ('хаки', 'Зелений'), ('green', 'Зелений'),
    ('сер', 'Сірий'), ('сір', 'Сірий'), ('grey', 'Сірий'), ('gray', 'Сірий'),
    ('желт', 'Жовтий'), ('жовт', 'Жовтий'), ('гірчич', 'Жовтий'), ('горчич', 'Жовтий'),
    ('оранж', 'Помаранчевий'), ('помаранч', 'Помаранчевий'),
    ('фиолет', 'Ліловий'), ('фіолет', 'Ліловий'), ('лилов', 'Ліловий'), ('лілов', 'Ліловий'),
    ('золот', 'Золотий'), ('рептил', 'Анімалістичний'), ('питон', 'Анімалістичний'), ('пітон', 'Анімалістичний'),
]
MATERIAL = {'шкіра': 'Натуральна шкіра', 'кожа': 'Натуральна шкіра', 'натуральная кожа': 'Натуральна шкіра'}


def get(url, tries=6):
    for i in range(tries):
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (ELORA catalog import)'})
            with urlopen(req, timeout=40) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:
            if i == tries - 1:
                print(f'  ! {url}: {e}', file=sys.stderr)
                return ''
            time.sleep(min(2 ** (i + 1), 30))


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def listing(slug):
    """Картки категорії з усіх сторінок: slug товару -> базові поля."""
    out, n = {}, 1
    while True:
        url = f'{BASE}/catalog/{slug}' + (f'/page-{n}' if n > 1 else '')
        page = get(url)
        if not page:
            sys.exit(f'Не вдалося завантажити {url} — імпорт зупинено, щоб не залишити неповний каталог')
        cards = page.split('<div class="product_preview fn_product">')[1:]
        new = 0
        for c in cards:
            m = re.search(r'href="/products/([^"]+)"', c)
            opt = re.search(r'<option[^>]*data-price="([^"]+)"[^>]*data-stock="([^"]*)"', c)
            if not m or not opt or m.group(1) in out:
                continue
            name = re.search(r'product_preview__name_link[^>]*>\s*([^<]+)', c)
            img = re.search(r'data-src="([^"]+/files/resized/products/[^"]+)"', c)
            out[m.group(1)] = {
                'slug': m.group(1),
                't': clean(name.group(1)) if name else None,
                'p': float(re.sub(r'[^\d.]', '', opt.group(1).replace(',', '.')) or 0),
                'stock': int(opt.group(2) or 0) if opt.group(2).isdigit() else 0,
                'cover': img.group(1) if img else None,
            }
            new += 1
        if not new or f'/catalog/{slug}/page-{n + 1}"' not in page:
            return list(out.values())
        n += 1


def details(slug):
    page = get(f'{BASE}/products/{slug}')
    if not page:
        return {}
    gal = page.split('gallery-thumbs')[0]
    imgs = list(dict.fromkeys(re.findall(r'<a href="([^"]+/files/resized/products/[^"]+)" data-fancybox', gal)))
    feats = {clean(k).rstrip(':'): clean(v) for k, v in re.findall(
        r'features__name"><span>(.*?)</span></div>\s*<div class="features__value">(.*?)</div>', page, re.S)}
    desc = re.search(r'block__description--style">(.*?)</div>', page, re.S)
    old = re.search(r'data-old-price="([^"]+)"|fn_old_price[^>]*>([\d\s]+)<', page)
    return {'imgs': imgs, 'feats': feats, 'desc': clean(desc.group(1)) if desc else '',
            'old': float(re.sub(r'\D', '', next(g for g in old.groups() if g))) if old else None}


def color(title, feats):
    src = f"{feats.get('Колір', '')} {feats.get('Цвет', '')} {title}".lower()
    for k, v in COLOR_RULES:
        if k in src:
            return v
    return None


def price(x, k):
    return x if k == 1 else round(x * k / 10) * 10


IMG_DIR = 'img/4c'


def fetch_bytes(url, tries=6):
    for i in range(tries):
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (ELORA catalog import)'})
            with urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                print(f'  ! фото {url}: {e}', file=sys.stderr)
                return None
            time.sleep(min(2 ** (i + 1), 30))


def localize(url):
    """URL фото 4cases -> img/4c/<назва>.webp (качає, якщо ще немає). None, якщо не вдалося."""
    if not url.startswith('http'):
        return url
    from PIL import Image
    stem = re.sub(r'\.\d+x\d+\.\w+$', '', url.rsplit('/', 1)[-1])
    stem = re.sub(r'[^\w.-]+', '-', stem).strip('-.') or hashlib.md5(url.encode()).hexdigest()[:12]
    path = f'{IMG_DIR}/{stem}.webp'
    if os.path.exists(path):
        return path
    raw = fetch_bytes(url)
    if not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw))
        if im.mode in ('RGBA', 'LA', 'P'):
            im = im.convert('RGBA')
            bg = Image.new('RGB', im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im = im.convert('RGB')
        im.thumbnail((700, 800))
        im.save(path, 'WEBP', quality=80, method=6)
        return path
    except Exception as e:
        print(f'  ! фото {url}: {e}', file=sys.stderr)
        return None


def localize_all(data, workers=2):
    os.makedirs(IMG_DIR, exist_ok=True)
    urls = sorted({u for p in data for u in p['img'] if u.startswith('http')})
    with ThreadPoolExecutor(workers) as ex:
        local = dict(zip(urls, ex.map(localize, urls)))
    for p in data:
        p['img'] = [local.get(u, u) for u in p['img'] if local.get(u, u)]
    keep = {u for p in data for u in p['img']}
    for f in os.listdir(IMG_DIR):          # прибрати фото товарів, яких більше немає
        if f'{IMG_DIR}/{f}' not in keep:
            os.remove(f'{IMG_DIR}/{f}')
    lost = sum(1 for v in local.values() if not v)
    print(f'фото: {len(keep)} локально, не вдалося: {lost}')
    return [p for p in data if p['img']]


def write(path, data, cats):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('/* ÉLORA — сумки та аксесуари, зібрано з 4cases.com.ua скриптом import_4cases.py */\n')
        f.write('const DATA_4C=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
        f.write('const CATS_4C=' + json.dumps(cats, ensure_ascii=False, separators=(',', ':')) + ';\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--markup', type=float, default=1.0, help='множник до цін сайту (опт -> роздріб)')
    ap.add_argument('--out', default='data/4cases.js')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--no-images', action='store_true', help='не качати фото, лишити посилання на 4cases')
    ap.add_argument('--images-only', action='store_true', help='лише локалізувати фото в наявному файлі')
    a = ap.parse_args()

    if a.images_only:
        src = open(a.out, encoding='utf-8').read()
        data = json.loads(re.search(r'const DATA_4C=(\[.*?\]);\n', src, re.S).group(1))
        cats = json.loads(re.search(r'const CATS_4C=(\[.*?\]);\n', src, re.S).group(1))
        data = localize_all(data)
        for c in cats:
            c['n'] = sum(1 for p in data if p['c'] == c['name'])
        write(a.out, data, [c for c in cats if c['n']])
        return

    data, cats, seen = [], {}, set()
    for slug, name in CATS:
        rows = [r for r in listing(slug) if r['stock'] > 0 and r['p'] > 0 and r['slug'] not in seen]
        seen.update(r['slug'] for r in rows)
        with ThreadPoolExecutor(a.workers) as ex:
            info = list(ex.map(details, [r['slug'] for r in rows]))
        n = 0
        for r, d in zip(rows, info):
            imgs = d.get('imgs') or ([r['cover']] if r['cover'] else [])
            if not (r['t'] and imgs):
                continue
            feats = d.get('feats', {})
            mat = feats.get('Матеріал') or feats.get('Материал') or ''
            sp = {'Розмір': m.group(0).replace('*', ' × ') + ' мм'} if (m := re.match(r'\d{2,4}\*\d{2,4}(\*\d{2,4})?', d.get('desc', ''))) else {}
            sp.update({k: v for k, v in feats.items() if k not in ('Колір', 'Цвет', 'Матеріал', 'Материал')})
            if r['stock'] <= 2:
                sp['Залишок'] = f"{r['stock']} шт."
            old = d.get('old')
            data.append({
                'id': '4c-' + r['slug'], 't': r['t'], 'c': name, 'cs': slug, 'b': '4cases',
                'p': price(r['p'], a.markup), 'o': price(old, a.markup) if old and old > r['p'] else None,
                'col': color(r['t'], feats), 'mat': MATERIAL.get(mat.lower(), mat) or 'Натуральна шкіра',
                'sz': [], 'img': imgs[:6], 'sp': sp,
            })
            n += 1
        print(f'  {name}: {n}', flush=True)
        if n:
            c = cats.setdefault(name, {'name': name, 'slug': slug, 'n': 0})
            c['n'] += n

    cats = list(cats.values())
    if not a.no_images:
        data = localize_all(data)
        for c in cats:
            c['n'] = sum(1 for p in data if p['c'] == c['name'])
        cats = [c for c in cats if c['n']]
    write(a.out, data, cats)
    print(json.dumps({'products': len(data), 'categories': len(cats), 'out': a.out}, ensure_ascii=False))


if __name__ == '__main__':
    main()
