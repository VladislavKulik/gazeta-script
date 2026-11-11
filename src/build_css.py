#!/usr/bin/env python3
"""Склеює css/*.css у один style.css (порядок = префікс імені файлу: 00-, 01-, …).

    python build_css.py            # читабельна збірка → style.css
    python build_css.py --min      # стиснута збірка (без коментарів і зайвих пробілів)

Ваш render.py і далі читає один style.css — його код змінювати не треба.
Поклали модулі в інше місце? Змініть SRC/OUT нижче.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC, OUT = ROOT / 'css', ROOT / 'style.css'
# рядки та url(...) (зокрема data:-URI) не чіпаємо
KEEP = re.compile(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|url\((?:[^()"\']|"[^"]*"|\'[^\']*\')*\))')

def minify(css: str) -> str:
    out = []
    for i, part in enumerate(KEEP.split(css)):
        if i % 2:                      # літерал
            out.append(part); continue
        part = re.sub(r'/\*.*?\*/', '', part, flags=re.S)
        part = re.sub(r'\s+', ' ', part)
        part = re.sub(r'\s*([{};,>+~])\s*', r'\1', part)       # навколо розділювачів
        part = re.sub(r':\s+', ':', part)
        part = part.replace(';}', '}')
        part = re.sub(r'(?<![\d.])0\.(\d)', r'.\1', part)            # 0.5 → .5
        out.append(part)
    return ''.join(out).strip() + '\n'

def main() -> None:
    files = sorted(SRC.glob('*.css'))
    if not files: sys.exit(f'немає файлів у {SRC}')
    css = '\n'.join(f.read_text(encoding='utf-8') for f in files)
    if '--min' in sys.argv: css = minify(css)
    OUT.write_text(css, encoding='utf-8')
    print(f'{OUT.name}: {len(files)} модулів, {len(css.encode()):,} байт' + (' (min)' if '--min' in sys.argv else ''))

if __name__ == '__main__':
    main()
