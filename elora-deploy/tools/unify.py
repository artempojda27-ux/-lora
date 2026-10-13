# -*- coding: utf-8 -*-
"""
Єдиний фон для фото товарів: вирізає товар (rembg, модель isnet-general-use) і ставить
його по центру на фірмове тло ÉLORA (холодний світло-сірий, як у каталогах галерейного типу) з легкою тінню.
Канва 4:5 (800×1000), WebP.

    python3 tools/unify.py img/4c img/tp img/pd   # обробити всі ще не оброблені фото
Оброблені файли записуються поверх оригіналів, їхні назви — в img/.unified (щоб не обробляти двічі).
Модулем: from tools.unify import unify_file
"""
import io, os, sys
from PIL import Image, ImageFilter, ImageDraw

W, H = 800, 1000
BG_TOP, BG_BOTTOM = (238, 239, 241), (221, 223, 227)   # #EEEFF1 -> #DDDFE3
MARK = 'img/.unified'
_session = None


def _bg():
    bg = Image.new('RGB', (W, H), BG_TOP)
    d = ImageDraw.Draw(bg)
    for y in range(H):                                  # вертикальний градієнт
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    glow = Image.new('L', (W, H), 0)                    # м'яке світло зверху по центру
    ImageDraw.Draw(glow).ellipse((W * .05, -H * .25, W * .95, H * .55), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.composite(Image.new('RGB', (W, H), (248, 249, 250)), bg, glow)


BG = None


def grade(im):
    """Фото з моделлю: кадр 4:5 і стримане холодне тонування в палітрі ÉLORA."""
    from PIL import ImageOps, ImageEnhance
    im = ImageOps.fit(im.convert('RGB'), (W, H), Image.LANCZOS, centering=(.5, .45))
    im = ImageEnhance.Color(im).enhance(.72)
    im = ImageEnhance.Contrast(im).enhance(1.06)
    r, g, b = im.split()
    r = r.point(lambda v: min(255, round(v * .97)))
    g = g.point(lambda v: min(255, round(v * .99 + 1)))
    b = b.point(lambda v: min(255, round(v * 1.03 + 4)))
    return Image.merge('RGB', (r, g, b))


def unify(im):
    """PIL image -> PIL RGB 800×1000 з товаром на єдиному тлі."""
    global _session, BG
    from rembg import new_session, remove
    if _session is None:
        _session = new_session('isnet-general-use')
        BG = _bg()
    cut = remove(im.convert('RGB'), session=_session)            # RGBA
    # чистий край: прибрати напівпрозорі «привиди», підтягнути щільність
    a = cut.getchannel('A').point(lambda v: 0 if v < 70 else min(255, round((v - 70) * 255 / 120)))
    box = a.getbbox()
    if not box:
        return None
    # кадр із моделлю (предмет упирається в край кадру) — вирізати чисто не вийде:
    # лишаємо фото, але приводимо до тієї ж теплої палітри й формату
    m = 3
    if box[1] <= m or box[0] <= m or box[2] >= cut.width - m:
        return grade(im)
    cut.putalpha(a)
    cut = cut.crop(box)
    s = min(W * .78 / cut.width, H * .74 / cut.height)
    cut = cut.resize((max(1, round(cut.width * s)), max(1, round(cut.height * s))), Image.LANCZOS)
    x, y = (W - cut.width) // 2, round(H * .53 - cut.height / 2)
    out = BG.copy()
    # контактна тінь: стиснута по висоті, розмита
    sh = Image.new('L', (W, H), 0)
    sw = cut.width * .82
    ImageDraw.Draw(sh).ellipse((W / 2 - sw / 2, y + cut.height - 16, W / 2 + sw / 2, y + cut.height + 22), fill=95)
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    out.paste(Image.new('RGB', (W, H), (70, 74, 82)), (0, 0), sh)
    # м'яка тінь від самого предмета
    drop = Image.new('L', (W, H), 0)
    drop.paste(cut.getchannel('A').point(lambda v: v * .22), (x + 6, y + 14))
    out.paste(Image.new('RGB', (W, H), (52, 56, 64)), (0, 0), drop.filter(ImageFilter.GaussianBlur(22)))
    out.paste(cut, (x, y), cut)
    return out


def done_set():
    try:
        return set(open(MARK, encoding='utf-8').read().split())
    except FileNotFoundError:
        return set()


def mark(paths):
    with open(MARK, 'a', encoding='utf-8') as f:
        f.writelines(p + '\n' for p in paths)


def unify_file(path):
    """Обробити файл на місці. True — успіх (або вже оброблений).
    ELORA_UNIFY_LATER=1 — лише скачати, обробити потім пачкою: python3 tools/unify.py img/…"""
    if os.environ.get('ELORA_UNIFY_LATER') or path in done_set():
        return True
    try:
        out = unify(Image.open(path))
        if out is None:
            return False
        out.save(path, 'WEBP', quality=82, method=6)
        mark([path])
        return True
    except Exception as e:
        print(f'  ! {path}: {e}', file=sys.stderr)
        return False


if __name__ == '__main__':
    done = done_set()
    todo = [f'{d}/{f}' for d in sys.argv[1:] if os.path.isdir(d) for f in sorted(os.listdir(d))
            if f.endswith('.webp') and f'{d}/{f}' not in done]
    print(f'до обробки: {len(todo)}', flush=True)
    for i, p in enumerate(todo, 1):
        unify_file(p)
        if i % 50 == 0:
            print(f'  {i}/{len(todo)}', flush=True)
    print('готово', flush=True)
