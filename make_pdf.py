#!/usr/bin/env python3
"""PDF-версія випуску для телефонів, де HTML відкривається без JavaScript (Quick Look на iPhone, перегляд у месенджерах).

    python make_pdf.py випуск.html                  # → випуск.pdf
    python make_pdf.py випуск.html -o out.pdf      # власне ім'я
    python make_pdf.py випуск.html --theme dark    # темна тема (за замовчуванням — світла)

Сторінка відкривається в Chromium З ВИМКНЕНИМ JavaScript — так само, як її побачить телефон без скриптів: новини та «Детально»
лежать у розмітці готовими блоками <section class="page">. Скрипт лише розкладає їх у друкований порядок: головна → усі
новини, кожна з нової сторінки → «Детально». Внутрішні посилання лишаються справжніми якорями PDF (плитка → новина,
«До випуску» → назад до плитки). Ігри в PDF неможливі — на їхньому місці стоїть підказка відкрити HTML у браузері.

Потрібно (один раз):  pip install playwright pypdf   &&   playwright install chromium
(pypdf необов'язковий: лише записує назву в метадані PDF.)
"""
import argparse
import sys
from pathlib import Path

# Сторінка розміром з екран телефона: так спрацьовують мобільні брейкпоінти сайту, а текст читається без масштабування.
DEFAULT_WIDTH, DEFAULT_HEIGHT = 430, 932

PDF_CSS = """
html, body { height: auto !important; }
/* залипання в PDF повторюється на кожній сторінці — вимикаємо */
.masthead, .masthead__bar, .article-nav { position: static !important; }
* { animation: none !important; transition: none !important; }

/* усі сторінки видно, кожна з нової (звичайно їх показує :target) */
.page { display: block !important; break-before: page; }

/* не різати картки навпіл між сторінками */
.news-tile, .widget, .gallery__item, .chat__msg, .quotes__msg, .short__item, .stats-detail__section,
.stats-detail__kpi, .game-card, .empty-card, .article-next, figure { break-inside: avoid; }
/* картка статистики майже на всю сторінку */
.widget--stats { zoom: 0.93; }          /* щоб картка влізла в одну сторінку 430×932, а кнопка не їхала на порожню */
.stats__chart, .stats__top, .stats__leaders li { break-inside: avoid; }
h1, h2, h3, .section-head { break-after: avoid; }      /* заголовок секції не лишається внизу сторінки без вмісту */
.article__prose p { orphans: 3; widows: 3; }
"""

# Розкладає документ у друкований порядок. Виконується в браузері (без скриптів сторінки).
BUILD_JS = r"""
({ theme, css }) => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const main = $('#view-main'), content = $('#content');
  if (!main || !content) throw new Error('Не схоже на готовий випуск: немає #view-main / #content');
  document.documentElement.dataset.theme = theme;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);   // add_style_tag без JS зависає

  // Головна — першою: у розмітці сторінки новин стоять перед нею (для :target)
  content.prepend(main);

  // Ліниве завантаження вимикаємо: невидимі картинки інакше не завантажаться ніколи
  $$('img').forEach(i => { i.loading = 'eager'; i.decoding = 'sync'; });
  $$('video').forEach(v => v.removeAttribute('autoplay'));
  return { pages: $$('section.page').length, articles: $$('section.page[data-news]').length };
}
"""

# Стан завантаження — синхронний опит (проміси на сторінці без скриптів не завершуються)
READY_JS = "() => [...document.images].every(i => i.complete) && document.fonts.status !== 'loading'"


def main() -> int:
    ap = argparse.ArgumentParser(description='PDF-версія випуску для телефонів без JS')
    ap.add_argument('html', type=Path, help='готовий HTML випуску')
    ap.add_argument('-o', '--out', type=Path, help='куди зберегти PDF (за замовчуванням — поруч, з тим самим іменем)')
    ap.add_argument('--theme', choices=('light', 'dark'), default='light')
    ap.add_argument('--width', type=int, default=DEFAULT_WIDTH, help=f'ширина сторінки, px (за замовчуванням {DEFAULT_WIDTH})')
    ap.add_argument('--height', type=int, default=DEFAULT_HEIGHT, help=f'висота сторінки, px (за замовчуванням {DEFAULT_HEIGHT})')
    args = ap.parse_args()

    src = args.html.resolve()
    if not src.is_file():
        return print(f'Немає файлу: {src}', file=sys.stderr) or 1
    out = (args.out or src.with_suffix('.pdf')).resolve()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return print('Потрібен playwright:  pip install playwright && playwright install chromium', file=sys.stderr) or 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={'width': args.width, 'height': args.height}, color_scheme=args.theme,
                                  java_script_enabled=False)      # як на телефоні без скриптів: режим «без JS» самого випуску
        page = ctx.new_page()
        page.goto(src.as_uri())
        page.wait_for_load_state('load')
        info = page.evaluate(BUILD_JS, {'theme': args.theme, 'css': PDF_CSS})     # синхронний evaluate працює й за вимкненого JS сторінки
        for _ in range(40):                                       # до 8 с чекаємо на зображення й шрифти
            if page.evaluate(READY_JS):
                break
            page.wait_for_timeout(200)
        page.emulate_media(media='screen')                        # лишаємо екранний вигляд, а не друкований
        page.wait_for_timeout(150)
        title = page.title()
        opts = dict(path=str(out), width=f'{args.width}px', height=f'{args.height}px', print_background=True,
                    margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'})
        try:
            page.pdf(outline=True, tagged=True, **opts)           # закладки за заголовками; потрібен Playwright ≥ 1.42
        except TypeError:
            page.pdf(**opts)
        browser.close()

    try:
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter(clone_from=PdfReader(str(out)))
        w.add_metadata({'/Title': title, '/Producer': 'make_pdf.py'})
        with open(out, 'wb') as f:
            w.write(f)
    except ImportError:
        pass

    print(f'{out.name}: {info["articles"]} новин, {info["pages"] - info["articles"]} розділів «Детально», {out.stat().st_size // 1024} КБ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
