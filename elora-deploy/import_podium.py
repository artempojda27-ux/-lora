# -*- coding: utf-8 -*-
"""
podium.ua -> data/podium.js (відділ «Сумки та аксесуари», ті самі категорії, що й 4cases)

    python3 import_podium.py --feed 'https://…xml'   # повний каталог з XML-вивантаження Podium
    python3 import_podium.py                          # стартова добірка: перші сторінки підкатегорій

Повний каталог Podium віддає дропшипінг-партнерам у форматі XML (оптова реєстрація
«Інтернет-Магазин» на podium.ua/opt/). Посторінковий обхід каталогу заборонений у
їхньому robots.txt (Disallow: /*page=), тому без фіду беремо лише перші сторінки
підкатегорій. Беремо тільки те, що в наявності. Перші два фото кожної моделі
зберігаються локально (img/pd) і ставляться на єдиний фон (tools/unify.py).
"""
import argparse, html, json, os, re, sys, time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

BASE = 'https://podium.ua'
CATS = [   # підкатегорія Podium -> категорія вітрини (як у 4cases)
    ('ua/womens-bags/classic',                 'Жіночі сумки'),
    ('ua/womens-bags',                         'Жіночі сумки'),
    ('ua/womens-bags/clutches',                'Клатчі та косметички'),
    ('ua/cosmetic-bags',                       'Клатчі та косметички'),
    ('ua/wallets/womens',                      'Жіночі гаманці'),
    ('ua/mens-bags/sumki-na-poyas-na-plecho',  'Чоловічі сумки'),
    ('ua/mens-bags/tablets',                   'Чоловічі сумки'),
    ('ua/mens-bags/documents',                 'Чоловічі сумки'),
    ('ua/mens-bags/briefcases',                'Портфелі'),
    ('ua/rucksacks/city',                      'Рюкзаки'),
    ('ua/womens-bags/backpacks',               'Рюкзаки'),
    ('ua/wallets/mens',                        'Портмоне'),
    ('ua/belts/mens',                          'Ремені'),
]
SLUG = {'Жіночі сумки': 'zhinochi-sumky', 'Клатчі та косметички': 'klatchi', 'Жіночі гаманці': 'zhinochi-gamantsi',
        'Чоловічі сумки': 'cholovichi-sumky', 'Портфелі': 'portfeli', 'Рюкзаки': 'ryukzaky',
        'Портмоне': 'portmone', 'Ремені': 'remeni'}
# категорія з назви (для XML-фіду, де категорії Podium свої)
NAME_RULES = [('клатч', 'Клатчі та косметички'), ('косметич', 'Клатчі та косметички'),
              ('портфел', 'Портфелі'), ('рюкзак', 'Рюкзаки'), ('ремін', 'Ремені'), ('ремен', 'Ремені'), ('пояс', 'Ремені'),
              ('портмоне', 'Портмоне'), ('гаманець чоловіч', 'Портмоне'), ('кошелек мужск', 'Портмоне'),
              ('гаманець', 'Жіночі гаманці'), ('кошел', 'Жіночі гаманці'),
              ('чоловіч', 'Чоловічі сумки'), ('мужск', 'Чоловічі сумки'), ('сумка', 'Жіночі сумки')]
MATERIALS = [('замш', 'Натуральна замша'), ('нейлон', 'Нейлон'), ('штучн', 'Штучна шкіра'), ('іск', 'Штучна шкіра'),
             ('еко', 'Штучна шкіра'), ('текстил', 'Текстиль'), ('шкір', 'Натуральна шкіра'), ('кожа', 'Натуральна шкіра')]
COLORS = [('black', 'Чорний'), ('чорн', 'Чорний'), ('brown', 'Коричневий'), ('коричн', 'Коричневий'), ('coffee', 'Коричневий'),
          ('cognac', 'Рудий'), ('caramel', 'Рудий'), ('camel', 'Бежевий'), ('beige', 'Бежевий'), ('беж', 'Бежевий'),
          ('khaki', 'Зелений'), ('green', 'Зелений'), ('olive', 'Зелений'), ('red', 'Червоний'), ('bordo', 'Бордовий'),
          ('burgundy', 'Бордовий'), ('wine', 'Бордовий'), ('blue', 'Синій'), ('navy', 'Синій'), ('grey', 'Сірий'),
          ('gray', 'Сірий'), ('white', 'Білий'), ('milk', 'Білий'), ('pink', 'Рожевий'), ('powder', 'Пудровий'),
          ('yellow', 'Жовтий'), ('orange', 'Помаранчевий'), ('purple', 'Ліловий'), ('lilac', 'Ліловий'), ('gold', 'Золотий')]
IMG_DIR = 'img/pd'
LOCAL_PHOTOS = 2


def get(url, tries=5, binary=False):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 (ELORA catalog import)'}), timeout=60) as r:
                b = r.read()
                return b if binary else b.decode('utf-8', 'replace')
        except Exception as e:
            if i == tries - 1:
                print(f'  ! {url}: {e}', file=sys.stderr)
                return None
            time.sleep(min(2 ** (i + 1), 30))


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def pick(rules, text, default=None):
    t = (text or '').lower()
    return next((v for k, v in rules if k in t), default)


def specs_from(desc):
    m = re.search(r'Розмір[^0-9]{0,12}(\d{1,3}(?:[.,]\d)?\s*[*xх×]\s*\d{1,3}(?:[.,]\d)?(?:\s*[*xх×]\s*\d{1,3}(?:[.,]\d)?)?)', desc or '')
    return {'Розмір': re.sub(r'\s*[*xх×]\s*', ' × ', m.group(1)) + ' см'} if m else {}


# ---------- стартова добірка з сайту ----------
def listing(path):
    page = get(f'{BASE}/{path}/') or ''
    out = []
    for c in page.split('class="products-item"')[1:]:
        m = re.search(r'href="(https://podium\.ua/ua/product/[^"]+)"', c)
        pid = re.search(r'data-id="(\d+)"', c)
        if m and pid:
            out.append((pid.group(1), m.group(1)))
    return out


def product(pid, url, cat):
    page = get(url)
    if not page:
        return None
    ld = {}
    for raw in re.findall(r'<script[^>]+ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            d = json.loads(raw, strict=False)
        except ValueError:
            continue
        if d.get('@type') == 'Product':
            ld = d
    offer = ld.get('offers') or {}
    if 'InStock' not in str(offer.get('availability', '')):
        return None
    price = float(offer.get('Price') or offer.get('price') or 0)
    imgs = list(dict.fromkeys([ld.get('image')] + sorted(set(
        u for u in re.findall(rf'https://podium\.ua/i/{pid}/[^"?\s]+\.jpg', page) if 'stat' not in u))))
    imgs = [u for u in imgs if u]
    title = clean(ld.get('name'))
    if not (title and price and imgs):
        return None
    desc = clean(ld.get('description'))
    return {'id': 'pd-' + pid, 't': title, 'c': cat, 'cs': SLUG[cat],
            'b': (ld.get('brand') or {}).get('name') or 'Podium', 'p': price, 'o': None,
            'col': pick(COLORS, title), 'mat': pick(MATERIALS, title, 'Натуральна шкіра'),
            'sz': [], 'img': imgs[:8], 'sp': specs_from(desc)}


def from_site(workers):
    seen, rows = set(), []
    for path, cat in CATS:
        items = [(pid, u) for pid, u in listing(path) if pid not in seen]
        seen.update(pid for pid, _ in items)
        with ThreadPoolExecutor(workers) as ex:
            got = [p for p in ex.map(lambda x: product(x[0], x[1], cat), items) if p]
        print(f'  {cat} ({path}): {len(got)}', flush=True)
        rows += got
    return rows


# ---------- повний каталог з XML (YML / Prom / Rozetka) ----------
def from_feed(src):
    raw = get(src, binary=True) if src.startswith('http') else open(src, 'rb').read()
    if not raw:
        sys.exit('Фід Podium не завантажився — каталог не змінено')
    root = ET.fromstring(raw)
    cats = {c.get('id'): (c.text or '') for c in root.iter('category')}
    rows = []
    for o in root.iter('offer'):
        if o.get('available', 'true').lower() in ('false', '0'):
            continue
        t = lambda tag: (o.findtext(tag) or '').strip()
        name = t('name_ua') or t('name') or t('model')
        price = float((t('price') or '0').replace(',', '.') or 0)
        imgs = [p.text.strip() for p in o.findall('picture') if p.text]
        if not (name and price and imgs):
            continue
        params = {p.get('name', ''): (p.text or '').strip() for p in o.findall('param')}
        cat = pick(NAME_RULES, f"{name} {cats.get(t('categoryId'), '')}")
        if not cat:
            continue
        old = float((t('oldprice') or '0').replace(',', '.') or 0)
        rows.append({'id': 'pd-' + (o.get('id') or t('vendorCode')), 't': name, 'c': cat, 'cs': SLUG[cat],
                     'b': t('vendor') or 'Podium', 'p': price, 'o': old if old > price else None,
                     'col': pick(COLORS, f"{params.get('Колір', '')} {params.get('Цвет', '')} {name}"),
                     'mat': pick(MATERIALS, f"{params.get('Матеріал', '')} {params.get('Материал', '')} {name}", 'Натуральна шкіра'),
                     'sz': [], 'img': imgs[:8], 'sp': specs_from(t('description_ua') or t('description'))})
    return rows


def localize(rows, workers):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tools.unify import unify_file
    from PIL import Image
    import io
    os.makedirs(IMG_DIR, exist_ok=True)

    def one(u):
        name = re.sub(r'[^\w.-]+', '-', '-'.join(u.split('/')[-2:])).rsplit('.', 1)[0]
        path = f'{IMG_DIR}/{name}.webp'
        if not os.path.exists(path):
            b = get(u, binary=True)
            if not b:
                return u, None
            try:
                im = Image.open(io.BytesIO(b)).convert('RGB')
                im.thumbnail((1000, 1250))
                im.save(path, 'WEBP', quality=86, method=6)
            except Exception as e:
                print(f'  ! {u}: {e}', file=sys.stderr)
                return u, None
        unify_file(path)
        return u, path

    urls = sorted({u for r in rows for u in r['img'][:LOCAL_PHOTOS]})
    with ThreadPoolExecutor(workers) as ex:
        local = dict(ex.map(one, urls))
    for r in rows:
        r['img'] = [local.get(u) or u for u in r['img'][:LOCAL_PHOTOS]] + r['img'][LOCAL_PHOTOS:]
    keep = {u for r in rows for u in r['img']}
    for f in os.listdir(IMG_DIR):
        if f'{IMG_DIR}/{f}' not in keep:
            os.remove(f'{IMG_DIR}/{f}')
    return sum(1 for v in local.values() if v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feed', help='URL або файл XML-вивантаження Podium')
    ap.add_argument('--markup', type=float, default=1.0)
    ap.add_argument('--out', default='data/podium.js')
    ap.add_argument('--workers', type=int, default=3)
    a = ap.parse_args()

    rows = from_feed(a.feed) if a.feed else from_site(a.workers)
    seen, uniq = set(), []
    for r in rows:
        if r['id'] not in seen:
            seen.add(r['id']); uniq.append(r)
    if a.markup != 1:
        for r in uniq:
            r['p'] = round(r['p'] * a.markup / 10) * 10
            r['o'] = round(r['o'] * a.markup / 10) * 10 if r['o'] else None
    n_img = localize(uniq, 2)

    counts = {}
    for r in uniq:
        counts.setdefault(r['c'], {'name': r['c'], 'slug': r['cs'], 'n': 0})['n'] += 1
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('/* ÉLORA — сумки та аксесуари Podium (podium.ua), зібрано скриптом import_podium.py */\n')
        f.write('const DATA_PD=' + json.dumps(uniq, ensure_ascii=False, separators=(',', ':')) + ';\n')
        f.write('const CATS_PD=' + json.dumps(list(counts.values()), ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(json.dumps({'products': len(uniq), 'categories': len(counts), 'photos_local': n_img,
                      'source': 'feed' if a.feed else 'site'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
