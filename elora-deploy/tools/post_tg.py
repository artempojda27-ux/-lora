# -*- coding: utf-8 -*-
"""
Публікація товарів із Telegram-постачальників (data/tg.js) у канал магазину.

    TELEGRAM_BOT_TOKEN=... python3 tools/post_tg.py --state state/posted.json        # один пост
    python3 tools/post_tg.py --state state/posted.json --dry                          # показати, що піде наступним

Щоразу публікує N найсвіжіших товарів, яких ще не було в каналі (новинки — першими,
залишки — поступово). Ціна — та сама, що на сайті (наценка з data/prices.js, як у pricing.js).
Фото бере з сайту; товар, чиї фото ще не задеплоєні, чекає наступного запуску.
Вночі (22:00–08:00 за Києвом) нічого не публікує. Стан — у JSON-файлі (окрема гілка tg-state).
"""
import argparse, datetime, html, json, os, re, sys, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.environ.get('ELORA_SITE', 'https://elora-shoes.com')


def js_const(path, name):
    m = re.search(rf'const {name}=(\[[\s\S]*?\]|\{{[\s\S]*?\}});', open(path, encoding='utf-8').read())
    return json.loads(m.group(1)) if m else None


def end(v, mode):
    v = max(0, v)
    if mode == '99':
        return max(99, round((v + 1) / 100) * 100 - 1)
    if mode == '79':
        return max(79, round((v - 79) / 100) * 100 + 79)
    return round(v / 10) * 10


def by_rule(v, r):
    if v is None or not r:
        return v
    k, a = float(r.get('k') or 1), float(r.get('a') or 0)
    if k == 1 and not a:
        return v
    return end(v * k + a, r.get('end'))


def site_price(p, rules, own):
    """те саме, що ELORA_PRICE.price у pricing.js"""
    m = own.get(p['id'])
    if m and m.get('p') is not None:
        return m['p'], m.get('o')
    r = rules.get('tg')
    pr = by_rule(p['p'], r)
    o = by_rule(p['o'], r) if p.get('o') else None
    return pr, (o if o and o > pr else None)


def money(n):
    return f'{int(n):,}'.replace(',', ' ') + ' ₴'


def sizes(sz):
    if not sz:
        return ''
    n = [int(x) for x in sz if x.isdigit()]
    if len(n) == len(sz) and len(n) > 2 and n == list(range(n[0], n[-1] + 1)):
        return f'{n[0]}–{n[-1]}'
    return ', '.join(sz)


def caption(p, price, old):
    e = html.escape
    tag = '#' + re.sub(r'\W+', '_', p['c'].lower()).strip('_')
    lines = [f"<b>{e(p['t'])}</b>", '']
    if p.get('col'):
        lines.append(f"Колір: {e(p['col'])}")
    if p['sp'].get('Матеріал'):
        lines.append(f"Матеріал: {e(p['sp']['Матеріал'])}")
    if p['sp'].get('Підклад'):
        lines.append(f"Всередині: {e(p['sp']['Підклад'])}")
    if sizes(p['sz']):
        lines.append(f"{'Розмір' if len(p['sz']) == 1 else 'Розміри'}: {sizes(p['sz'])}")
    lines += ['', f"<b>{money(price)}</b>" + (f"  <s>{money(old)}</s>" if old else ''), '',
              f"<a href=\"{SITE}/#p={p['id']}\">🛍 Замовити на сайті</a>", '', tag + ' #elora']
    return '\n'.join(lines)[:1024]


def tg(token, method, payload):
    req = Request(f'https://api.telegram.org/bot{token}/{method}', data=json.dumps(payload).encode(),
                  headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except HTTPError as e:
        return json.loads(e.read() or b'{}')


def jpeg(path):
    from PIL import Image
    import io
    im = Image.open(path).convert('RGB')
    b = io.BytesIO(); im.save(b, 'JPEG', quality=90); return b.getvalue()


def tg_files(token, method, fields, files):
    """multipart: fields — звичайні поля (dict/list -> JSON), files — {ім'я: (файл, байти)}"""
    import uuid
    bnd = uuid.uuid4().hex
    body = b''
    for k, v in fields.items():
        v = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        body += f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, data) in files.items():
        body += (f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                 f'Content-Type: image/jpeg\r\n\r\n').encode() + data + b'\r\n'
    body += f'--{bnd}--\r\n'.encode()
    req = Request(f'https://api.telegram.org/bot{token}/{method}', data=body,
                  headers={'Content-Type': f'multipart/form-data; boundary={bnd}'})
    try:
        with urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except HTTPError as e:
        return json.loads(e.read() or b'{}')


def oidc():
    """OIDC-токен GitHub Actions для /api/tg-post (потрібно permissions: id-token: write)"""
    url, tok = os.environ.get('ACTIONS_ID_TOKEN_REQUEST_URL'), os.environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN')
    if not url:
        return None
    with urlopen(Request(url + '&audience=elora-tg-post', headers={'Authorization': f'Bearer {tok}'}), timeout=30) as r:
        return json.loads(r.read())['value']


def via_site(jwt, cap, files):
    """публікація через сайт: токен бота живе у Vercel, тут лише підпис GitHub"""
    import base64
    body = json.dumps({'caption': cap, 'photos': [base64.b64encode(d).decode() for _, d in files.values()]}).encode()
    req = Request(f'{SITE}/api/tg-post', data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {jwt}'})
    try:
        with urlopen(req, timeout=120) as r:
            j = json.loads(r.read())
    except HTTPError as e:
        j = json.loads(e.read() or b'{}')
        j.setdefault('error_code', e.code)
    return {'ok': j.get('ok'), 'result': [{'message_id': i} for i in j.get('ids', [])],
            'description': j.get('error'), 'error_code': j.get('code') or j.get('error_code')}


def reachable(url):
    try:
        with urlopen(Request(url, method='HEAD', headers={'User-Agent': 'ELORA'}), timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', required=True)
    ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--force', action='store_true', help='ігнорувати нічну паузу')
    a = ap.parse_args()

    hour = datetime.datetime.now(ZoneInfo('Europe/Kyiv')).hour
    if not (a.force or a.dry) and not (8 <= hour < 22):
        print('нічна пауза'); return

    items = js_const(os.path.join(ROOT, 'data/tg.js'), 'DATA_TG') or []
    rules = js_const(os.path.join(ROOT, 'data/prices.js'), 'RULES') or {}
    own = js_const(os.path.join(ROOT, 'data/prices.js'), 'PRICES') or {}
    chat = json.load(open(os.path.join(ROOT, 'config/tg_sources.json'), encoding='utf-8'))['post_to']
    state = json.load(open(a.state, encoding='utf-8')) if os.path.exists(a.state) else {'posted': {}}
    posted = state.setdefault('posted', {})

    queue = sorted([p for p in items if p['k'] not in posted], key=lambda p: p.get('at') or '', reverse=True)
    print(f'у черзі: {len(queue)}, уже в каналі: {len(posted)}')
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    jwt = None if (token or a.dry) else oidc()
    if not (token or jwt or a.dry):
        sys.exit('немає TELEGRAM_BOT_TOKEN і це не GitHub Actions')
    done = 0
    for p in queue:
        if done >= a.n:
            break
        photos = [f"{SITE}/{x}" for x in p['img'][:3]]
        price, old = site_price(p, rules, own)
        cap = caption(p, price, old)
        if a.dry:
            print(cap, '\n', photos); done += 1; continue
        if not reachable(photos[0]):        # товар ще не задеплоєний — посилання «Замовити» поки не відкриється
            print(f"  ще не на сайті: {p['id']}"); continue
        # фото — з локальної копії, у JPEG (WebP за посиланням Telegram може не прийняти як фото)
        local = [os.path.join(ROOT, x) for x in p['img'][:3] if os.path.exists(os.path.join(ROOT, x))]
        files = {f'f{i}': (f'{i}.jpg', jpeg(x)) for i, x in enumerate(local)}
        media = [{'type': 'photo', 'media': f'attach://f{i}'} for i in range(len(files))]
        if not media:
            continue
        media[0].update({'caption': cap, 'parse_mode': 'HTML'})
        if jwt:
            r = via_site(jwt, cap, files)
        else:
            r = tg_files(token, 'sendMediaGroup', {'chat_id': chat, 'media': media}, files)
        if not r.get('ok') and token:          # запасний варіант — одне фото з підписом
            r = tg_files(token, 'sendPhoto', {'chat_id': chat, 'caption': cap, 'parse_mode': 'HTML', 'photo': 'attach://f0'},
                         {'f0': files['f0']})
        if not r.get('ok'):
            print(f"  ! {p['id']}: {r.get('description')}", file=sys.stderr)
            if r.get('error_code') in (400, 401, 403) and re.search(r'rights|not found|forbidden|auth|admin', str(r.get('description')), re.I):
                print('::warning::Бот не може публікувати в канал — додайте його адміністратором з правом публікації')
                break                                  # спробуємо в наступний запуск, без падіння workflow
            continue
        res = r['result'][0] if isinstance(r['result'], list) else r['result']
        posted[p['k']] = {'id': p['id'], 'msg': res.get('message_id'), 'at': datetime.datetime.utcnow().isoformat(timespec='seconds')}
        print(f"  ✓ {p['t']} — {money(price)}")
        done += 1
        time.sleep(3)
    if not a.dry:
        os.makedirs(os.path.dirname(os.path.abspath(a.state)), exist_ok=True)
        json.dump(state, open(a.state, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
