# -*- coding: utf-8 -*-
"""
4cases.com.ua -> data/4cases.js
Шкіряна галантерея (сумки, гаманці, ремені) для відділу «Сумки та аксесуари».

    python3 import_4cases.py                 # усі категорії, ціни як на сайті
    python3 import_4cases.py --markup 1.6    # роздрібна націнка до оптових цін

Скрипт обходить категорії (сторінки ?page=all), збирає посилання на товари
і з кожної картки бере назву, ціну, фото та характеристики. Джерела даних
по черзі: JSON-LD Product, мікророзмітка itemprop, og:* теги, галерея <img>.
Лише стандартна бібліотека Python.
"""
import argparse, html, json, re, sys, time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = 'https://4cases.com.ua'
# відомі розділи; решта знаходиться на головній за посиланнями /catalog/<slug>
SEED_CATS = ['zhenskie-sumki', 'muzhskie-sumki', 'zhenskie-koshelki', 'remni']
CAT_NAMES = {   # укр. назви для вітрини; невідомі slug беруться з <h1> категорії
    'zhenskie-sumki': 'Жіночі сумки', 'muzhskie-sumki': 'Чоловічі сумки',
    'zhenskie-koshelki': 'Жіночі гаманці', 'muzhskie-koshelki': 'Чоловічі гаманці',
    'remni': 'Ремені', 'portmone': 'Портмоне', 'klatchi': 'Клатчі',
    'ryukzaki': 'Рюкзаки', 'oblozhki': 'Обкладинки', 'vizitnitsy': 'Візитниці',
}
COLORS = ['Чорний', 'Коричневий', 'Бежевий', 'Білий', 'Червоний', 'Бордовий', 'Сірий',
          'Синій', 'Зелений', 'Рожевий', 'Пудровий', 'Рудий', 'Жовтий', 'Блакитний',
          'Золотий', 'Ліловий', 'Помаранчевий']
COLOR_RU = {'черн': 'Чорний', 'чорн': 'Чорний', 'коричн': 'Коричневий', 'беж': 'Бежевий',
            'бел': 'Білий', 'біл': 'Білий', 'красн': 'Червоний', 'червон': 'Червоний',
            'бордо': 'Бордовий', 'сер': 'Сірий', 'сір': 'Сірий', 'син': 'Синій',
            'зел': 'Зелений', 'роз': 'Рожевий', 'рож': 'Рожевий', 'пудр': 'Пудровий',
            'рыж': 'Рудий', 'руд': 'Рудий', 'желт': 'Жовтий', 'жовт': 'Жовтий',
            'голуб': 'Блакитний', 'блакит': 'Блакитний', 'золот': 'Золотий'}


def get(url, tries=4):
    for i in range(tries):
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (ELORA catalog import)'})
            with urlopen(req, timeout=30) as r:
                return r.read().decode(r.headers.get_content_charset() or 'utf-8', 'replace')
        except Exception as e:
            if i == tries - 1:
                print(f'  ! {url}: {e}', file=sys.stderr)
                return ''
            time.sleep(2 ** (i + 1))


def links(page, base):
    return {urljoin(base, html.unescape(h)).split('#')[0]
            for h in re.findall(r'href=["\']([^"\']+)["\']', page)}


def same_site(u):
    return urlparse(u).netloc.replace('www.', '') == urlparse(BASE).netloc


def cat_slug(u):
    m = re.match(r'^/catalog/([\w-]+)/?$', urlparse(u).path)
    return m and m.group(1)


def meta(page, prop):
    m = re.search(r'<meta[^>]+(?:property|name|itemprop)=["\']%s["\'][^>]*content=["\']([^"\']*)' % re.escape(prop), page) \
        or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name|itemprop)=["\']%s["\']' % re.escape(prop), page)
    return html.unescape(m.group(1)).strip() if m else None


def text(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()


def num(x):
    if x is None:
        return None
    m = re.search(r'\d[\d\s ]*(?:[.,]\d+)?', str(x))
    return float(re.sub(r'[\s ]', '', m.group(0)).replace(',', '.')) if m else None


def jsonld_product(page):
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if d.get('@type') in ('Product', ['Product']):
                    return d
                stack.extend(d.get('@graph', []))
    return {}


def color_of(title, specs):
    src = (specs.get('Колір') or specs.get('Цвет') or title).lower()
    for k, v in COLOR_RU.items():
        if k in src:
            return v
    return None


def parse_product(url, page, cat):
    ld = jsonld_product(page)
    offers = ld.get('offers') or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    title = ld.get('name') or text((re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S) or [None, ''])[1]) \
        or meta(page, 'og:title')
    price = num(offers.get('price') or offers.get('lowPrice') or meta(page, 'price')
                or meta(page, 'product:price:amount')
                or (re.search(r'class=["\'][^"\']*price[^"\']*["\'][^>]*>(.*?)<', page, re.S) or [None, None])[1])
    old = num((re.search(r'class=["\'][^"\']*(?:old|was)[-_]?price[^"\']*["\'][^>]*>(.*?)<', page, re.S) or [None, None])[1])

    imgs = ld.get('image') or []
    imgs = [imgs] if isinstance(imgs, str) else [i.get('url') if isinstance(i, dict) else i for i in imgs]
    if not imgs and meta(page, 'og:image'):
        imgs = [meta(page, 'og:image')]
    # фото з галереї картки: великі зображення товару, без іконок і логотипів
    for src in re.findall(r'(?:data-zoom-image|data-large|data-src|href|src)=["\']([^"\']+\.(?:jpe?g|png|webp))', page, re.I):
        u = urljoin(url, src)
        if re.search(r'logo|icon|sprite|banner|payment|flag', u, re.I):
            continue
        if u not in imgs and ('product' in u.lower() or 'upload' in u.lower() or 'image' in u.lower()):
            imgs.append(u)
    imgs = [urljoin(url, i) for i in imgs if i][:6]

    # характеристики: таблиці/списки «Назва: значення»
    specs = {}
    for k, v in re.findall(r'<(?:td|th|dt|span|div)[^>]*>\s*([^<:]{2,40}?)\s*:?\s*</(?:td|th|dt|span|div)>\s*'
                           r'<(?:td|dd|span|div)[^>]*>(.*?)</(?:td|dd|span|div)>', page, re.S):
        k, v = text(k), text(v)
        if k and v and len(v) < 120 and not re.search(r'ціна|цена|грн|кошик|корзин', k, re.I):
            specs.setdefault(k, v)

    mat = specs.get('Матеріал') or specs.get('Материал')
    sku = ld.get('sku') or specs.get('Артикул') or specs.get('Код')
    return {
        'id': '4c-' + (str(sku) if sku else urlparse(url).path.strip('/').split('/')[-1]),
        't': title, 'c': cat['name'], 'cs': cat['slug'], 'b': (ld.get('brand') or {}).get('name') if isinstance(ld.get('brand'), dict) else (ld.get('brand') or '4cases'),
        'p': price, 'o': old if old and price and old > price else None,
        'col': color_of(title or '', specs), 'mat': mat or 'Натуральна шкіра',
        'sz': [], 'img': imgs,
        'sp': {k: v for k, v in specs.items() if k not in ('Артикул', 'Код')} | ({'sku': str(sku)} if sku else {}),
        'url': url,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--markup', type=float, default=1.0, help='множник до цін сайту (опт -> роздріб)')
    ap.add_argument('--out', default='data/4cases.js')
    ap.add_argument('--delay', type=float, default=0.4, help='пауза між запитами, с')
    a = ap.parse_args()

    home = get(BASE + '/')
    slugs = list(dict.fromkeys(SEED_CATS + sorted(filter(None, (cat_slug(u) for u in links(home, BASE) if same_site(u))))))
    print('категорії:', ', '.join(slugs))

    data, cats, seen = [], [], set()
    for slug in slugs:
        cat_url = f'{BASE}/catalog/{slug}'
        page = get(cat_url + '?page=all')
        if not page:
            continue
        name = CAT_NAMES.get(slug) or text((re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S) or [None, slug])[1])
        cat = {'name': name, 'slug': slug}
        # товари: посилання всередині розділу глибше за саму категорію, або /product/...
        prods = sorted(u for u in links(page, cat_url) if same_site(u) and (
            urlparse(u).path.startswith(f'/catalog/{slug}/') or re.search(r'/(product|tovar|item)s?/', u)))
        n = 0
        for u in prods:
            if u in seen:
                continue
            seen.add(u)
            time.sleep(a.delay)
            pp = get(u)
            if not pp:
                continue
            p = parse_product(u, pp, cat)
            if not (p['t'] and p['p'] and p['img']):
                continue
            p['p'] = round(p['p'] * a.markup / 10) * 10 if a.markup != 1 else p['p']
            if p['o']:
                p['o'] = round(p['o'] * a.markup / 10) * 10 if a.markup != 1 else p['o']
            data.append(p)
            n += 1
        print(f'  {name}: {n} з {len(prods)} посилань')
        if n:
            cats.append({**cat, 'n': n})

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('/* ÉLORA — сумки та аксесуари, зібрано з 4cases.com.ua скриптом import_4cases.py */\n')
        f.write('const DATA_4C=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
        f.write('const CATS_4C=' + json.dumps(cats, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(json.dumps({'products': len(data), 'categories': len(cats), 'out': a.out}, ensure_ascii=False))


if __name__ == '__main__':
    main()
