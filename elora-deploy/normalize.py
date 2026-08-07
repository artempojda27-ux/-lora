# -*- coding: utf-8 -*-
"""
TAPULI feed normalizer
XML (standard platform) -> normalized JSON
product (slug) -> variants (group_id = color) -> sizes
"""
import xml.etree.ElementTree as ET
import json, re, sys
from collections import OrderedDict

SRC = sys.argv[1] if len(sys.argv) > 1 else '/mnt/user-data/uploads/price-xml'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'catalog.json'

# --- парсинг характеристик из свободного текста description ---
DESC_RULES = [
    ('heel',         r'(?:Зручний|Стійкий)?\s*Підбор\s*:?\s*([^\n]+)'),
    ('heel_height',  r'Висота підбор[уа]\s*:?\s*([^\n]+)'),
    ('shaft_height', r"Висота від п['\u2019]?яти\s*:?\s*([^\n]+)"),
    ('sole_material',r'Матеріал підошви\s*:?\s*([^\n]+)'),
    ('sole_back',    r'Підошва позаду\s*:?\s*([^\n]+)'),
    ('sole_front',   r'Підошва (?:спереду|попереду)\s*:?\s*([^\n]+)'),
    ('sole',         r'Підошва\s*:?\s*([^\n]+)'),
    ('insole',       r'Устілка\s*:?\s*([^\n]+)'),
    ('lining',       r'(?:Всередині|Підклад(?:ка)?)\s*:?\s*([^\n]+)'),
    ('material',     r'Матеріал\s*:?\s*([^\n]+)'),
    ('color_text',   r'Колір\s*:?\s*([^\n]+)'),
    ('shaft_girth',  r'Обхват гомілки/верху\s*:?\s*([^\n]+)'),
    ('decor',        r'Декор\s*:?\s*([^\n]+)'),
    ('country',      r'Виробництво\s*[-\u2013:]?\s*([^\n]+)'),
]

def parse_desc(text):
    out = {}
    if not text:
        return out
    for key, rx in DESC_RULES:
        m = re.search(rx, text)
        if m:
            out[key] = m.group(1).strip(' .;')
    return out

def money(x):
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None

root = ET.parse(SRC).getroot()

categories = {c.get('id'): {'slug': c.get('slug'), 'name': c.text}
              for c in root.findall('.//categories/category')}

products = OrderedDict()   # slug -> product
skipped = 0

for p in root.findall('.//products/product'):
    slug     = p.findtext('slug')
    group_id = p.get('group_id')
    size     = p.findtext('param[@name="Розмір"]')
    if not slug or not group_id:
        skipped += 1
        continue

    retail = money(p.find('price/retail').text if p.find('price/retail') is not None else None)
    old    = money(p.findtext('oldprice'))
    cat_el = p.find('categories/main')
    cat_id = cat_el.get('id') if cat_el is not None else None

    prod = products.get(slug)
    if prod is None:
        prod = products[slug] = {
            'slug': slug,
            'category_id': cat_id,
            'category': categories.get(cat_id, {}).get('name'),
            'category_slug': categories.get(cat_id, {}).get('slug'),
            'vendor': p.findtext('vendor'),
            'manufacturer': p.findtext('manufacturer'),
            'variants': OrderedDict(),
        }

    v = prod['variants'].get(group_id)
    if v is None:
        desc = p.findtext('description') or ''
        v = prod['variants'][group_id] = {
            'group_id': group_id,
            'sku': p.findtext('sku'),
            'title': p.findtext('title'),
            'url': p.findtext('url'),
            'color': p.findtext('param[@name="Колір"]'),
            'material': p.findtext('param[@name="Матеріал верху"]'),
            'price_retail': retail,
            'price_old': old,
            'on_sale': bool(old and retail and old > retail),
            'description': desc.strip(),
            'specs': parse_desc(desc),
            'photo_main': p.findtext('photos/main'),
            'photos': [ph.text for ph in p.findall('photos/photo') if ph.text],
            'updated_at': p.findtext('updated_at'),
            'sizes': [],
        }

    if size and size not in [s['size'] for s in v['sizes']]:
        v['sizes'].append({'size': size, 'offer_id': p.get('id'), 'available': p.get('available') == 'true'})

# сортировка размеров + сводка по товару
for prod in products.values():
    prod['variants'] = list(prod['variants'].values())
    for v in prod['variants']:
        v['sizes'].sort(key=lambda s: int(s['size']) if s['size'].isdigit() else 99)
        v['size_list'] = [s['size'] for s in v['sizes']]
    prices = [v['price_retail'] for v in prod['variants'] if v['price_retail']]
    prod['title'] = prod['variants'][0]['title']
    prod['photo_main'] = prod['variants'][0]['photo_main']
    prod['price_min'] = min(prices) if prices else None
    prod['price_max'] = max(prices) if prices else None
    prod['colors'] = len(prod['variants'])
    prod['sizes_total'] = sum(len(v['sizes']) for v in prod['variants'])
    prod['any_sale'] = any(v['on_sale'] for v in prod['variants'])

catalog = {
    'source': 'tapuli.shop standard XML',
    'currency': 'UAH',
    'categories': categories,
    'stats': {
        'products': len(products),
        'variants': sum(len(p['variants']) for p in products.values()),
        'offers': sum(p['sizes_total'] for p in products.values()),
        'skipped': skipped,
    },
    'products': list(products.values()),
}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(catalog, f, ensure_ascii=False, indent=1)

print(json.dumps(catalog['stats'], ensure_ascii=False))
