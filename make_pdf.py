#!/usr/bin/env python3
"""PDF-версія випуску для телефонів, де HTML відкривається без JavaScript (Quick Look на iPhone, перегляд у месенджерах).

    python make_pdf.py випуск.html                  # → випуск.pdf
    python make_pdf.py випуск.html -o out.pdf      # власне ім'я
    python make_pdf.py випуск.html --theme dark    # темна тема (за замовчуванням — світла)

Що відбувається: готовий HTML відкривається в Chromium, і з нього збирається «друкований» документ:
головна → усі новини по черзі (кожна з нової сторінки) → «Детально» для цифр дня/тижня. Інтерактив прибирається
(ігри, перемикач теми, «Хочу ще»), а внутрішні посилання стають справжніми якорями PDF: плитка веде на новину,
«Далі» — на наступну, «До випуску» — назад. Ігри в PDF неможливі — натомість стоїть підказка відкрити HTML у браузері.

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
/* залипання/фіксація в PDF повторюються на кожній сторінці — вимикаємо */
.masthead, .masthead__bar, .article-nav, .read-progress { position: static !important; }
* { animation: none !important; transition: none !important; }

/* кожна новина — з нової сторінки */
.pdf-article { break-before: page; padding-top: 4px; }
.pdf-detail  { break-before: page; }
.pdf-back { display: inline-block; margin: 0 0 14px; padding: 7px 14px; border-radius: 999px; background: var(--pill);
  color: var(--accent); font: 700 13px/1 var(--body); text-decoration: none; }

/* не різати картки навпіл між сторінками */
.news-tile, .widget, .gallery__item, .chat__msg, .quotes__msg, .short__item, .stats-detail__section,
.stats-detail__kpi, .game-card, .empty-card, .article-next, figure { break-inside: avoid; }
h1, h2, h3 { break-after: avoid; }
.article__prose p { orphans: 3; widows: 3; }
"""

# Збирає документ у вже відкритій сторінці. Виконується в браузері.
BUILD_JS = r"""
async ({ theme }) => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = document.documentElement;
  root.dataset.theme = theme;

  const main = $('#view-main'), content = $('#content');
  if (!main || !content) throw new Error('Не схоже на готовий випуск: немає #view-main / #content');
  main.style.display = 'block';

  // 1. Прибираємо інтерактив і службові елементи
  $$('.theme-toggle, dialog, .read-progress, .joke__actions, #articleHost').forEach(e => e.remove());

  // 2. Ігри недоступні — одна підказка замість обох блоків
  const gameSecs = ['gameTitle', 'wGameTitle'].map(id => { const h = document.getElementById(id); return h && h.closest('section'); }).filter(Boolean);
  if (gameSecs.length) {
    const note = document.createElement('section');
    note.className = 'section--spaced';
    note.innerHTML = '<div class="empty-card"><h2 class="u-display">Ігри — в інтерактивній версії</h2>' +
      '<p>Wordle, Тетріс, «Хто це сказав?» і Кросворд працюють лише в HTML-файлі, відкритому в браузері.</p></div>';
    gameSecs[0].replaceWith(note);
    gameSecs.slice(1).forEach(s => s.remove());
  }

  // 3. Обкладинки й медіа новин: у шаблоні вони лежать в одному екземплярі й підтягуються за data-ref
  const hydrate = typeof window.hydrate === 'function' ? window.hydrate : (frag) => {
    $$('[data-ref]', frag).forEach(el => {
      const src = $('#view-main [data-mid="' + el.getAttribute('data-ref') + '"]');
      if (!src) return;
      el.setAttribute('src', (src.getAttribute('src') || '').split('#')[0]);
      if (el.tagName === 'VIDEO' && src.getAttribute('poster') && !el.getAttribute('poster')) el.setAttribute('poster', src.getAttribute('poster'));
      el.removeAttribute('data-ref');
    });
  };

  const articles = document.createElement('div');
  articles.id = 'pdf-articles';
  const back = () => { const a = document.createElement('a'); a.className = 'pdf-back'; a.href = '#view-main'; a.textContent = '← До випуску'; return a; };
  $$('template[data-news]').forEach(tpl => {
    const sec = document.createElement('section');
    sec.className = 'pdf-article';
    sec.id = tpl.id.replace(/^tpl-/, '');
    const frag = tpl.content.cloneNode(true);
    hydrate(frag);
    sec.append(back(), frag);
    $$('.article-nav, .article-side, .read-progress, .also-card', sec).forEach(e => e.remove());
    articles.append(sec);
  });

  // 4. «Детально» з модальних вікон → розділи в кінці; кнопки стають посиланнями
  const detail = document.createElement('div');
  [['stats-day', '#statsDetail'], ['stats-week', '#weekStatsDetail']].forEach(([key, btnSel]) => {
    const tpl = document.getElementById('tpl-' + key), btn = $(btnSel);
    if (!tpl) { if (btn) btn.remove(); return; }
    const sec = document.createElement('section');
    sec.className = 'pdf-detail'; sec.id = 'pdf-' + key;
    const h = document.createElement('h2');
    h.className = 'u-display'; h.textContent = tpl.getAttribute('data-title') || 'Детально';
    sec.append(back(), h, tpl.content.cloneNode(true));
    detail.append(sec);
    if (btn) {
      const a = document.createElement('a');
      a.className = btn.className; a.href = '#pdf-' + key; a.innerHTML = btn.innerHTML;
      btn.replaceWith(a);
    }
  });
  main.after(articles, detail);

  // 5. Посилання: #main → головна; ті, що нікуди не ведуть (ігри), стають звичайним текстом
  $$('a[href^="#"]').forEach(a => {
    let id = a.getAttribute('href').slice(1);
    if (id === 'main') { id = 'view-main'; a.setAttribute('href', '#view-main'); }
    if (!id || !document.getElementById(id)) { a.removeAttribute('href'); a.removeAttribute('role'); }
  });
  $$('video').forEach(v => { v.removeAttribute('autoplay'); v.pause && v.pause(); });

  // 6. Дочекатися шрифтів і зображень. Ліниве завантаження вимикаємо: невидимі картинки інакше не завантажаться ніколи.
  $$('img').forEach(i => { i.loading = 'eager'; i.decoding = 'sync'; });
  const settle = Promise.all([document.fonts.ready, ...$$('img').map(i => i.decode ? i.decode().catch(() => { }) : null)]);
  await Promise.race([settle, new Promise(r => setTimeout(r, 8000))]);       // не чекаємо довше 8 с
  return { articles: articles.children.length, detail: detail.children.length, games: gameSecs.length };
}
"""


def make_pdf(
    html: Path | str,
    out: Path | str | None = None,
    theme: str = 'light',
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> Path | None:
    """Генерує PDF-версію випуску з готового HTML."""
    src = Path(html).resolve()
    if not src.is_file():
        print(f'Немає файлу: {src}', file=sys.stderr)
        return None
    dest = (Path(out) if out else src.with_suffix('.pdf')).resolve()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Потрібен playwright:  pip install playwright && playwright install chromium', file=sys.stderr)
        return None

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={'width': width, 'height': height},
            color_scheme=theme,
            reduced_motion='reduce',
        )  # без анімацій появи: усе одразу в кінцевому вигляді
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(src.as_uri())
        page.wait_for_load_state('load')
        page.wait_for_timeout(300)  # скрипт сторінки (жарти, підсвітка) відпрацьовує після load
        info = page.evaluate(BUILD_JS, {'theme': theme})
        page.add_style_tag(content=PDF_CSS)
        page.emulate_media(media='screen')  # лишаємо екранний вигляд, а не друкований
        page.wait_for_timeout(150)
        title = page.title()
        opts = dict(
            path=str(dest),
            width=f'{width}px',
            height=f'{height}px',
            print_background=True,
            margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
        )
        try:
            page.pdf(outline=True, tagged=True, **opts)  # закладки за заголовками; потрібен Playwright ≥ 1.42
        except TypeError:
            page.pdf(**opts)
        browser.close()

    try:
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter(clone_from=PdfReader(str(dest)))
        w.add_metadata({'/Title': title, '/Producer': 'make_pdf.py'})
        with open(dest, 'wb') as f:
            w.write(f)
    except ImportError:
        pass

    for e in errors:
        print('Помилка в сторінці:', e, file=sys.stderr)
    print(f'{dest.name}: {info["articles"]} новин, {info["detail"]} розділів «Детально», {dest.stat().st_size // 1024} КБ')
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description='PDF-версія випуску для телефонів без JS')
    ap.add_argument('html', nargs='?', type=Path, help='готовий HTML випуску (за замовчуванням — найновіший у output/)')
    ap.add_argument('-o', '--out', type=Path, help='куди зберегти PDF (за замовчуванням — поруч, з тим самим іменем)')
    ap.add_argument('--theme', choices=('light', 'dark'), default='light')
    ap.add_argument('--width', type=int, default=DEFAULT_WIDTH, help=f'ширина сторінки, px (за замовчуванням {DEFAULT_WIDTH})')
    ap.add_argument('--height', type=int, default=DEFAULT_HEIGHT, help=f'висота сторінки, px (за замовчуванням {DEFAULT_HEIGHT})')
    args = ap.parse_args()

    html_file = args.html
    if not html_file:
        out_dir = Path(__file__).parent / 'output'
        candidates = sorted(out_dir.glob('*.html'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            return print(f'Не знайдено жодного HTML-файлу в {out_dir}', file=sys.stderr) or 1
        html_file = candidates[0]
        print(f'Використовується останній випуск: {html_file.name}')

    res = make_pdf(html_file, args.out, theme=args.theme, width=args.width, height=args.height)
    return 0 if res else 1


if __name__ == '__main__':
    sys.exit(main())
