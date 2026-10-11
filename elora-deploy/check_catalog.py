# -*- coding: utf-8 -*-
"""
Запобіжник для автооновлення: порівнює новий каталог із попереднім (git HEAD)
і не дає закомітити порожній або різко урізаний каталог.

    python3 check_catalog.py data/catalog.js DATA
    python3 check_catalog.py data/4cases.js DATA_4C

Код виходу 1, якщо моделей менше за --min-ratio від попередньої кількості
або менше --min-count; тоді workflow відкочує файл і фото.
"""
import argparse, json, re, subprocess, sys


def count(src, var):
    m = re.search(r'const %s=(\[.*?\]);\n' % var, src, re.S)
    return len(json.loads(m.group(1))) if m else 0


ap = argparse.ArgumentParser()
ap.add_argument('path')
ap.add_argument('var')
ap.add_argument('--min-ratio', type=float, default=0.5)
ap.add_argument('--min-count', type=int, default=30)
a = ap.parse_args()

new = count(open(a.path, encoding='utf-8').read(), a.var)
try:
    old_src = subprocess.run(['git', 'show', f'HEAD:./{a.path}'], capture_output=True, text=True, check=True).stdout
    old = count(old_src, a.var)
except subprocess.CalledProcessError:
    old = 0

print(f'{a.path}: було {old}, стало {new}')
if new < a.min_count or (old and new < old * a.min_ratio):
    print(f'::error::{a.path}: підозріло мало моделей ({new} проти {old}) — оновлення скасовано')
    sys.exit(1)
