# -*- coding: utf-8 -*-
"""
Telegram-канали постачальників -> data/tg.js (п'ятий постачальник вітрини, «Telegram»)

    python3 import_tg.py                    # усі канали з config/tg_sources.json
    python3 import_tg.py --days 14          # глибина історії
    python3 import_tg.py --dry              # лише розібрати й показати, нічого не писати

Читає відкриті веб-сторінки каналів t.me/s/<канал> (без бота й ключів). Постачальники
викладають альбом фото, а слідом — текст із ціною; імпорт склеює їх і бере з тексту
код, назву, ціну (дроп/опт або ціна; $ — за курсом НБУ), стару ціну, розміри, колір,
матеріал. Пости без ціни або без фото пропускаються. Товар живе на сайті, доки його пост
не старший за TTL днів (постачальники повторюють пости «знову в наявності» — тоді він
оновлюється). Перші LOCAL_PHOTOS фото зберігаються у WebP в img/tg.
Потрібні beautifulsoup4 і Pillow.
"""
import argparse, datetime, html, io, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

OUT = 'data/tg.js'
IMG_DIR = 'img/tg'
SOURCES = 'config/tg_sources.json'
LOCAL_PHOTOS = 3
TTL = 30                 # днів: товар зникає, якщо пост старший і не повторювався
UA = {'User-Agent': 'Mozilla/5.0 (ELORA catalog import)'}

# категорії вітрини: ключове слово в тексті -> (назва, slug, відділ)
CATS = [
    (r'ботфорт', 'Ботфорти', 'botforty', 'shoes'),
    (r'козак', 'Козаки', 'kozaky', 'shoes'),
    (r'напівчобот|полусапож', 'Напівчоботи', 'napivchoboty', 'shoes'),
    (r'чобот|сапог|сапож', 'Чоботи', 'choboty', 'shoes'),
    (r'ботильйон|ботильон|ботиль', 'Ботильйони', 'botyljony', 'shoes'),
    (r'челс', 'Черевики', 'cherevyky', 'shoes'),
    (r'черевик|ботин|дутик|сноубут', 'Черевики', 'cherevyky', 'shoes'),
    (r'угг|ugg', 'Уггі', 'uggi', 'shoes'),
    (r'лофер', 'Лофери', 'lofery', 'shoes'),
    (r'мокасин|топсайдер', 'Мокасини', 'mokasyny', 'shoes'),
    (r'балетк', 'Балетки', 'baletky', 'shoes'),
    (r'кросів|кроссов|снікер|сникер', 'Кросівки', 'krosivky', 'shoes'),
    (r'кеди|кеды|\bкед', 'Кеди', 'kedy', 'shoes'),
    (r'босоніж|босонож|сандал', 'Босоніжки', 'bosonizhky', 'shoes'),
    (r'шльопан|шлепан|капці|тапоч|мюл', 'Шльопанці', 'shlopanczi', 'shoes'),
    (r'сабо|клоги', 'Сабо', 'sabo', 'shoes'),
    (r'туфл|човник|лодочк|мері джейн|мэри джейн', 'Туфлі', 'tufli', 'shoes'),
    (r'рюкзак', 'Рюкзаки', 'ryukzaki', 'leather'),
    (r'клатч|косметичк', 'Клатчі та косметички', 'klatchi-ta-kosmetichki', 'leather'),
    (r'гаман|кошел', 'Жіночі гаманці', 'zhenskie-koshelki', 'leather'),
    (r'сумк|шопер|бананк', 'Жіночі сумки', 'zhenskie-sumki', 'leather'),
]
SKIP_TITLE = re.compile(r'^(знову в наявн|в наявн|доступн|акці|sale|розпродаж|тотальн|ціни нижче|розміри в наявн|'
                        r'останні розмір|код\b|були|було|новинк|new\b|хіт|топ\b|передзамовл|огляд|увага|‼|ціна)', re.I)
EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⠀▪-◾←-⇿]+')
NUM = r'(\d{1,3}(?:[  ]?\d{3})|\d{3,5})'


def fetch(url, tries=4, binary=False):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers=UA), timeout=40) as r:
                b = r.read()
                return b if binary else b.decode('utf-8', 'replace')
        except Exception as e:
            if i == tries - 1:
                print(f'  ! {url}: {e}', file=sys.stderr)
                return None
            time.sleep(2 ** (i + 1))


def usd_rate():
    """курс НБУ, грн за $; запасний — 41.5"""
    j = fetch('https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json')
    try:
        return float(json.loads(j)[0]['rate'])
    except Exception:
        return 41.5


def crawl(ch, days, max_pages):
    """повідомлення каналу за останні days днів: {id: {dt, text, ph}}"""
    from bs4 import BeautifulSoup
    cut = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    msgs, before = {}, None
    for _ in range(max_pages):
        h = fetch(f'https://t.me/s/{ch}' + (f'?before={before}' if before else ''))
        if not h:
            break
        s = BeautifulSoup(h, 'html.parser')
        ms = s.select('.tgme_widget_message[data-post]')
        if not ms:
            break
        old = False
        for m in ms:
            i = int(m['data-post'].split('/')[1])
            t = m.select_one('time[datetime]')
            dt = datetime.datetime.fromisoformat(t['datetime']) if t else None
            if dt and dt < cut:
                old = True
            body = m.select_one('.tgme_widget_message_text')
            if body:
                for br in body.find_all('br'):
                    br.replace_with('\n')
            ph = []
            for p in m.select('.tgme_widget_message_photo_wrap'):
                u = re.search(r"url\('([^']+)'", p.get('style', ''))
                if u:
                    ph.append(u.group(1))
            msgs[i] = {'dt': dt, 'text': body.get_text().strip() if body else '', 'ph': ph}
        before = min(int(m['data-post'].split('/')[1]) for m in ms)
        if old:
            break
        time.sleep(0.5)
    return msgs


def clean(s):
    s = EMOJI.sub(' ', html.unescape(s)).replace('«', '').replace('»', '').replace('"', '')
    return re.sub(r'[ \t\u00a0]+', ' ', s).strip(' -–—:;.,')


def num(s):
    return int(re.sub(r'\D', '', s))


def parse(text, rate):
    """з тексту поста -> поля товару або None"""
    t = text.replace(' ', ' ')
    low = t.lower()
    if re.search(r'#відеогляд|огляд зі складу|відгук', low) and not re.search(r'грн|\$', low):
        return None
    # ціна: дроп/опт -> «акційна ціна»/«ціна» -> будь-яке «N грн», крім старої
    price = None
    for pat in (rf'дроп\w*[^\d\n]{{0,25}}{NUM}\s*(?:грн|₴|uah)', rf'опт\w*[^\d\n]{{0,25}}{NUM}\s*(?:грн|₴|uah)',
                rf'(?:акційн\w* ціна|ціна|вартість)[^\d\n]{{0,15}}{NUM}\s*(?:грн|₴|uah)'):
        m = re.search(pat, low)
        if m:
            price = num(m.group(1)); break
    if price is None:
        for m in re.finditer(rf'{NUM}\s*(?:грн|₴|uah)', low):
            if not re.search(r'(був|було|стара|роздріб|рекоменд|передоплат|доплат|доставк|знижк|відшив|пошив)\w*[^\n]{0,25}$',
                             low[max(0, m.start() - 40):m.start()]):
                price = num(m.group(1)); break
    if price is None:
        m = re.search(r'(\d{2,4})\s*\$|\$\s*(\d{2,4})', low)
        if m:
            price = int(round(int(m.group(1) or m.group(2)) * rate, -1))
    if not price or not (150 <= price <= 60000):
        return None
    old = None
    m = re.search(rf'(?:був|були|було|стара ціна)\w*[^\d\n]{{0,12}}{NUM}', low)
    if m and num(m.group(1)) > price:
        old = num(m.group(1))

    lines = [clean(l) for l in t.split('\n')]
    lines = [l for l in lines if l]
    code = None
    m = re.search(r'(?:код|арт(?:икул)?\.?|модель)\s*[:№#-]?\s*([A-Za-zА-Яа-яІіЇїЄє]{0,3}-?\d[\w-]{1,12})', t, re.I)
    if m:
        code = m.group(1).strip('-')

    # категорія та назва
    cat = catpat = None
    for pat, name, slug, dept in CATS:
        if re.search(pat, low):
            cat, catpat = (name, slug, dept), pat; break
    if not cat:
        return None
    title = None
    for l in lines[:12]:
        if SKIP_TITLE.search(l) or re.search(r'\d{3,}\s*(грн|\$)|см\b|=', l.lower()):
            continue
        if re.search(catpat, l.lower()) and len(l) <= 60:
            title = l; break
    if not title:
        mm = re.search(r'модель\s*[«"]?([^\n«»"(]{2,30})', t, re.I)
        title = f'{cat[0]} {clean(mm.group(1))}' if mm else cat[0]
    title = re.sub(r'\s*(—|-)\s*$', '', title)
    title = title[0].upper() + title[1:]

    # розміри: діапазон «36-41» або рядки «39 = 25 см» / «36 - 23.5 см» (саме наявні)
    sz = []
    m = re.search(r'розмір\w*(?: ряд)?\s*[:—–-]?\s*(3[3-9]|4[0-6])\s*[-–—]\s*(3[4-9]|4[0-7])', low)
    if m and int(m.group(1)) < int(m.group(2)):
        sz = [str(x) for x in range(int(m.group(1)), int(m.group(2)) + 1)]
    else:
        for mm in re.finditer(r'(?m)^\W*(3[3-9]|4[0-6])\s*р?\.?\s*[=–—-]\s*\d{2}[.,]?\d?\s*см', t):
            if mm.group(1) not in sz:
                sz.append(mm.group(1))
    if cat[2] == 'shoes' and not sz:
        return None

    sp = {}
    m = re.search(r'матеріал\w*[^:\n—-]{0,20}[:—-]\s*([^\n;]{3,80})', t, re.I)
    if m and re.search(r'нат|шкір|замш|текст|лак|еко|нубук|хутр|вовн', m.group(1), re.I):
        sp['Матеріал'] = re.split(r',\s*(?:всередині|усередині)|\.\s', clean(m.group(1)))[0][:70]
    m = re.search(r'(?:^|\n)\W*(?:колір|кольори|цвет)(?!\w*\s+підошв)\w*\s*[:—-]?\s*([^\n;]{2,50})', t, re.I)
    col = clean(m.group(1)).capitalize() if m else ''
    for k, pat in (('Підклад', r'(?:підклад\w*|підкладка|утеплювач|усередині|всередині)[ \t]*[:—-]?[ \t]*([^\n;]{3,60})'),
                   ('Підошва', r'висота підошви[ \t]*[:—-]?[ \t]*([^\n;]{2,40})'),
                   ('Каблук', r'(?:каблук|підбор)\w*[ \t]*[:—-]?[ \t]*(\d[^\n;]{0,30})'),
                   ('Виробництво', r'виробництв\w*[ \t]*[:—-]?[ \t]*([^\n;"]{2,40})')):
        m = re.search(pat, t, re.I)
        if m:
            sp[k] = re.sub(r'\s*\([^)]*(?:грн|\$)[^)]*\)', '', clean(m.group(1)))   # без доплат постачальника
    return {'t': title, 'code': code, 'p': price, 'o': old, 'sz': sz, 'col': col, 'c': cat[0], 'cs': cat[1], 'd': cat[2], 'sp': sp}


def products(ch, name, msgs, rate):
    """склеїти альбоми з текстами і розібрати"""
    ids = sorted(msgs)
    used, out = set(), []
    for n, i in enumerate(ids):
        m = msgs[i]
        if not m['text']:
            continue
        p = parse(m['text'], rate)
        if not p:
            continue
        ph = list(m['ph'])
        if not ph:          # фото — окремим альбомом перед текстом (у межах 15 хв і 15 повідомлень)
            for j in reversed(ids[max(0, n - 15):n]):
                a = msgs[j]
                if j in used or (a['text'] and parse(a['text'], rate)):
                    break
                if a['ph'] and m['dt'] and a['dt'] and (m['dt'] - a['dt']).total_seconds() <= 900:
                    ph = a['ph']; used.add(j); break
        if not ph:
            continue
        p.update({'id': f'tg-{ch}-{i}', 'ch': ch, 'sn': name, 'u': f'https://t.me/{ch}/{i}',
                  'k': f"{ch}|{p['code'] or p['t']}|{p['col']}".lower(),
                  'img': ph[:8], 'at': m['dt'].isoformat() if m['dt'] else None})
        out.append(p)
    # один товар (канал + код + колір) — лише найсвіжіший пост
    seen, uniq = set(), []
    for p in sorted(out, key=lambda x: x['at'] or '', reverse=True):
        key = (p['code'] or p['t'].lower(), p['col'].lower(), p['p'] if not p['code'] else 0)
        if key in seen:
            continue
        seen.add(key); uniq.append(p)
    return uniq


def localize(rows, workers):
    from PIL import Image, ImageOps
    os.makedirs(IMG_DIR, exist_ok=True)

    def one(job):
        pid, n, u = job
        path = f'{IMG_DIR}/{pid[3:]}-{n}.webp'
        if os.path.exists(path):
            return u, path
        b = fetch(u, binary=True)
        if not b:
            return u, None
        try:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(b))).convert('RGB')
            im.thumbnail((720, 960))
            im.save(path, 'WEBP', quality=82, method=6)
            return u, path
        except Exception as e:
            print(f'  ! {u}: {e}', file=sys.stderr)
            return u, None

    jobs = [(r['id'], n, u) for r in rows for n, u in enumerate(r['img'][:LOCAL_PHOTOS])]
    with ThreadPoolExecutor(workers) as ex:
        got = dict(ex.map(one, jobs))
    for r in rows:
        local = [got.get(u) for u in r['img'][:LOCAL_PHOTOS]]
        r['img'] = [x for x in local if x]
    return [r for r in rows if r['img']]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=21)
    ap.add_argument('--pages', type=int, default=40, help='не більше сторінок на канал за запуск')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--show', type=int, default=4)
    ap.add_argument('--cache', help='тека для кешу сторінок каналів (налагодження)')
    a = ap.parse_args()
    src = json.load(open(SOURCES, encoding='utf-8'))
    rate = usd_rate()

    prev = {}
    if os.path.exists(OUT):
        m = re.search(r'const DATA_TG=(\[[\s\S]*?\]);', open(OUT, encoding='utf-8').read())
        prev = {p['id']: p for p in json.loads(m.group(1))} if m else {}

    fresh, stats = [], {}
    for s in src['channels']:
        cache = a.cache and os.path.join(a.cache, s['ch'] + '.json')
        if cache and os.path.exists(cache):          # для налагодження: не качати канал заново
            msgs = {int(k): {**v, 'dt': datetime.datetime.fromisoformat(v['dt']) if v['dt'] else None}
                    for k, v in json.load(open(cache, encoding='utf-8')).items()}
        else:
            msgs = crawl(s['ch'], a.days, a.pages)
            if cache:
                os.makedirs(a.cache, exist_ok=True)
                json.dump({k: {**v, 'dt': v['dt'].isoformat() if v['dt'] else None} for k, v in msgs.items()},
                          open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
        rows = products(s['ch'], s['name'], msgs, rate)
        stats[s['ch']] = {'posts': len(msgs), 'products': len(rows)}
        fresh += rows
        print(f"{s['ch']}: {len(msgs)} повідомлень -> {len(rows)} товарів", file=sys.stderr)
    if a.dry:
        for ch in {p['ch'] for p in fresh}:
            for p in [x for x in fresh if x['ch'] == ch][:a.show]:
                print(json.dumps({k: p[k] for k in ('id', 't', 'p', 'o', 'sz', 'col', 'c', 'code', 'sp')}, ensure_ascii=False), len(p['img']))
        print(json.dumps(stats, ensure_ascii=False))
        return

    # нове з каналів + те, що вже було на сайті й ще не прострочене (сторінки каналу могли не дійти так глибоко)
    cut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=TTL)).isoformat()
    by = {}
    for p in fresh:
        by[p['id']] = p
    keys = {(p['ch'], p['code'] or p['t'].lower(), p['col'].lower()) for p in fresh}
    for p in prev.values():
        if p['id'] in by or not p.get('at') or p['at'] < cut:
            continue
        if (p['ch'], p.get('code') or p['t'].lower(), p.get('col', '').lower()) in keys:
            continue                       # той самий товар уже є свіжішим постом
        if all(os.path.exists(x) for x in p['img']):
            by[p['id']] = p
    rows = [r for r in by.values() if r['id'] in prev and r is prev[r['id']]]
    rows += localize([r for r in by.values() if not (r['id'] in prev and r is prev[r['id']])], a.workers)
    rows.sort(key=lambda r: r['at'] or '', reverse=True)

    keep = {x for r in rows for x in r['img']}
    if os.path.isdir(IMG_DIR):
        for f in os.listdir(IMG_DIR):
            if f'{IMG_DIR}/{f}' not in keep:
                os.remove(f'{IMG_DIR}/{f}')

    data = [{k: r.get(k) for k in ('id', 'k', 'ch', 'sn', 'u', 't', 'code', 'c', 'cs', 'd', 'p', 'o', 'col', 'sz', 'img', 'sp', 'at')} for r in rows]
    cats = {}
    for r in data:
        c = cats.setdefault((r['c'], r['d']), {'name': r['c'], 'slug': r['cs'], 'd': r['d'], 'n': 0})
        c['n'] += 1
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('/* ÉLORA — товари з Telegram-каналів постачальників (import_tg.py). */\n')
        f.write('const DATA_TG=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
        f.write('const CATS_TG=' + json.dumps(sorted(cats.values(), key=lambda c: -c['n']), ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(json.dumps({'products': len(data), 'usd': rate, **stats}, ensure_ascii=False))


if __name__ == '__main__':
    main()
