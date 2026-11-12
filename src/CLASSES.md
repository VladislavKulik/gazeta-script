# Імена класів: стандарт і таблиця міграції

## Стандарт

Єдина схема — **BEM у kebab-case**:

| Що | Шаблон | Приклад |
|---|---|---|
| Блок | `block` | `news-tile`, `widget`, `modal` |
| Елемент | `block__element` | `news-tile__cover`, `quiz__option` |
| Модифікатор | `block--modifier` | `widget--hero`, `btn--primary` |
| Стан (ставить JS) | `is-*` / `has-*` | `is-active`, `is-correct`, `has-value` |
| Утиліта | `u-*` | `u-display` |

Правила: один компонент — один файл у `src/css/`; стан не вкладається в ім'я блока (`is-current`, а не `chip-on`); абревіатур на 1–3 літери більше немає (`ai`, `tp`, `k6` → `also-link`, `tetro-logo__piece`, `stats__tick`).

Стани зведено в один словник — той самий `is-correct` тепер і в Wordle, і в вікторині, і в легенді; `is-active` — і в крапках вікторини, і в підказках кросворду.

## Класи від бекенду (page_data.py не змінювався)

Python і далі віддає старі імена — шаблон перекладає їх словниками на початку макросів:

| Бекенд віддає | Шаблон видає |
|---|---|
| `main-lead` | `news-tile--lead` |
| `main-small` | `news-tile--small` |
| `ms-12` | `news-tile--w12` |
| `ms-6` | `news-tile--w6` |
| `ms-4` | `news-tile--w4` |
| `ms-tall` | `news-tile--tall` |
| `ms-solo` | `news-tile--solo` |
| `m-photo` | `media-photo` |
| `m-sticker` | `media-sticker` |
| `m-gif` | `media-gif` |

Якщо бекенд почне віддавати новий клас — додайте рядок у `TILE_CLASS` / `MEDIA_KIND` у `template.html`; невідомі класи проходять без змін (`TILE_CLASS.get(c, c)`).

## Змінні CSS, з якими працюють JS і розмітка (не перейменовувались)

`--card`, `--pill`, `--hi`, `--accent`, `--good` (читає Тетріс), `--absent`, `--cs`, `--fade-t`, `--fade-b` (ставить JS), `--p`, `--h`, `--w`, `--rd` (inline у розмітці).

## Видалено як мертве

Класи без жодного посилання в HTML та JS (правила видалено з CSS): `.ai-title`, `.arr-close`, `.arr-plus`, `.article-date-chip`, `.article-lead`, `.btn-sm`, `.footer`, `.label`, `.media-counts`, `.play-btn`, `.st-detail`, `.st-submetric__lbl`, `.w-copy-btn`, `.w-res-title`, `.w-result`, `.w-why-text`.
Маркер `t` у 28 віджетах — на нього не було жодного правила, прибрано з розмітки.

## Режим без JS (iPhone Quick Look, перегляд у месенджерах)

Той самий файл і той самий шаблон. Клас `js` на `<html>` ставить скрипт; якщо його немає, спрацьовують правила `html:not(.js)`
з `css/12-nojs.css`.

| Клас / id | Що робить |
|---|---|
| `page`, `page--detail` | сторінка-блок (новина, «Детально»); схована завжди, без JS її показує `:target`, зі скриптом скрипт забирає її з документа |
| `page__body` | вміст «Детально» — саме його скрипт кладе в модальне вікно |
| `page__chrome`, `page__title` | шапка сторінки «Детально» (кнопка «назад» і заголовок), потрібна лише без JS |
| `u-nojs-only` / `u-js-only` | видно лише без скрипта / лише зі скриптом |
| `joke__static` | усі анекдоти списком замість стеку з «Хочу ще» |
| `game-note` | підказка «ігри — лише в браузері» |
| `id="tile-<slug>"` | якір плитки: кнопка «До випуску» без JS веде на неї |
| `id="statsDetail-link"`, `id="weekStatsDetail-link"` | посилання «Детально» для режиму без JS (кнопки `#statsDetail` / `#weekStatsDetail` лишилися для скрипта) |
| `data-back` | на кнопці «До випуску»: зі скриптом вона веде на головну, без — на плитку |

Сторінки новин у розмітці стоять **перед** `#view-main` у `<main id="content">`: головну без JS ховає сусідній селектор
`.page:target ~ #view-main` (він працює на всіх iOS, на відміну від `:has()`).

Змінна шаблону **`inline_covers`** (за замовчуванням `true`): додає обкладинкам на сторінках новин власну копію даних, щоб вони
були видимі без JS. `false` — файл менший, але без скрипта обкладинки на сторінках новин не показуються (піктограм-«зламаних»
картинок не буде: вони ховаються). Відео без JS показує лише постер.

## Таблиця «було → стало»


### каркас

| Було | Стало |
|---|---|
| `top` | `masthead__bar` |
| `chips` | `masthead__chips` |
| `on` | `is-current` |
| `sp` | `chip--weekly` |
| `theme` | `theme-toggle` |
| `th-i` | `theme-toggle__icon` |
| `th-t` | `theme-toggle__label` |
| `header` | `masthead__header` |
| `htext` | `masthead__text` |
| `logo-link` | `masthead__logo` |
| `hacc` | `masthead__logo-accent` |
| `footer-brand` | `site-footer__brand` |
| `footer-note` | `site-footer__note` |
| `footer-legal` | `site-footer__legal` |

### типографіка й секції

| Було | Стало |
|---|---|
| `disp` | `u-display` |
| `lbl` | `kicker` |
| `sub` | `section-head__sub` |
| `sub--wk` | `section-head__sub--week` |
| `sec-mt` | `section--spaced` |
| `week-first` | `section--week-first` |
| `week-sep` | `week-divider` |
| `dispute-wrapper` | `section--spaced` |
| `overheard-grid` | `widget-grid--overheard` |

### кнопки, значки, стрілки

| Було | Стало |
|---|---|
| `btn-cta` | `btn--primary` |
| `btn-back` | `btn--back` |
| `ico` | `icon` |
| `ico-go` | `icon--go` |
| `ico-l` | `icon--left` |
| `ico-r` | `icon--right` |
| `ico-ne` | `icon--ne` |
| `ico-mo` | `icon--more` |
| `arr` | `arrow` |
| `arr-se` | `arrow--se` |
| `arr-l` | `arrow--left` |
| `arr-r` | `arrow--right` |
| `arr-u` | `arrow--up` |
| `arr-d` | `arrow--down` |
| `arr-ok` | `arrow--check` |

### плитки «Головне»

| Було | Стало |
|---|---|
| `main-news` | `news-grid` |
| `tile` | `news-tile` |
| `cover` | `news-tile__cover` |
| `tile-top` | `news-tile__top` |
| `category` | `category-tag` |
| `tile-read` | `news-tile__read` |
| `card-copy` | `news-tile__copy` |
| `day-chip` | `news-tile__day` |
| `tile-sub` | `news-tile__sub` |
| `go` | `news-tile__go` |
| `no-cover` | `news-tile--plain` |
| `nc-0` | `news-tile--tone-0` |
| `nc-1` | `news-tile--tone-1` |
| `nc-2` | `news-tile--tone-2` |
| `main-lead` | `news-tile--lead` |
| `main-small` | `news-tile--small` |
| `ms-12` | `news-tile--w12` |
| `ms-6` | `news-tile--w6` |
| `ms-4` | `news-tile--w4` |
| `ms-tall` | `news-tile--tall` |
| `ms-solo` | `news-tile--solo` |

### віджети «Ще за день» і родичі

| Було | Стало |
|---|---|
| `widget-tile` | `widget` |
| `tile-head` | `widget__head` |
| `tile-label` | `widget__label` |
| `eyemeta` | `widget__meta` |
| `is-solo` | `widget--solo` |
| `span-7` | `widget--w7` |
| `span-5` | `widget--w5` |
| `tile--hero` | `widget--hero` |
| `tile--sticker` | `widget--sticker` |
| `tile--short` | `widget--short` |
| `tile--joke` | `widget--joke` |
| `tile--stats` | `widget--stats` |
| `tile--dialog` | `widget--dialog` |
| `tile--qts` | `widget--quotes` |
| `tile--meme` | `widget--meme` |
| `tile--award` | `widget--award` |
| `hero-copy` | `hero__copy` |
| `hero-name` | `hero__name` |
| `hero-role` | `hero__role` |
| `hero-desc` | `hero__desc` |
| `hero-bottom` | `hero__bottom` |
| `hero-number` | `hero__number` |
| `sticker-stage` | `sticker__stage` |
| `sticker-bottom` | `sticker__bottom` |
| `sticker-note` | `sticker__note` |
| `sticker-mark` | `sticker__mark` |
| `stk` | `sticker-img` |
| `stk-emoji` | `sticker-img--emoji` |
| `short-list` | `short__list` |
| `short-item` | `short__item` |
| `short-num` | `short__num` |
| `joke-main` | `joke__main` |
| `joke-mark` | `joke__mark` |
| `joke-stack` | `joke__stack` |
| `joke-text` | `joke__text` |
| `joke-actions` | `joke__actions` |
| `meme-word` | `meme__word` |
| `meme-sub` | `meme__sub` |
| `meme-def` | `meme__def` |
| `meme-example` | `meme__example` |
| `aw-0` | `award--tone-0` |
| `aw-1` | `award--tone-1` |
| `aw-2` | `award--tone-2` |
| `aw-3` | `award--tone-3` |
| `aw-4` | `award--tone-4` |
| `aw-5` | `award--tone-5` |
| `aw-who` | `award__who` |
| `aw-ava` | `award__avatar` |
| `aw-name` | `award__name` |
| `aw-val` | `award__value` |
| `aw-num` | `award__num` |
| `aw-unit` | `award__unit` |
| `aw-note` | `award__note` |
| `dlg-chat` | `chat` |
| `dlg-msg` | `chat__msg` |
| `dlg-alt` | `chat__msg--alt` |
| `dlg-ava` | `avatar` |
| `dlg-body` | `chat__body` |
| `d-meta` | `chat__meta` |
| `d-sender` | `chat__sender` |
| `d-time` | `chat__time` |
| `d-bubble` | `chat__bubble` |
| `qt-chat` | `quotes` |
| `qt-msg` | `quotes__msg` |

### «Цифри дня/тижня»

| Було | Стало |
|---|---|
| `stats-redesign` | `stats` |
| `st-grid` | `stats__grid` |
| `st-total` | `stats__total` |
| `st-number` | `stats__number` |
| `st-unit` | `stats__unit` |
| `st-submetrics` | `stats__subs` |
| `st-submetric` | `stats__sub` |
| `st-submetric__val` | `stats__sub-value` |
| `st-chart` | `stats__chart` |
| `st-chart-head` | `stats__chart-head` |
| `st-bars` | `stats__bars` |
| `st-axis` | `stats__axis` |
| `st-axis--week` | `stats__axis--week` |
| `k6` | `stats__tick` |
| `st-top` | `stats__top` |
| `st-top-head` | `stats__top-head` |
| `st-leaders` | `stats__leaders` |
| `rank` | `stats__rank` |
| `name` | `stats__name` |
| `count` | `stats__count` |
| `bar` | `stats__bar` |
| `peak` | `is-peak` |
| `has` | `has-value` |
| `st-foot` | `stats__foot` |
| `st-foot-note` | `stats__foot-note` |

### «Детально» (модалка)

| Було | Стало |
|---|---|
| `sd` | `stats-detail` |
| `sd--week` | `stats-detail--week` |
| `sd-kpis` | `stats-detail__kpis` |
| `sd-kpi` | `stats-detail__kpi` |
| `sd-kpi-hi` | `stats-detail__kpi--hi` |
| `sd-sec` | `stats-detail__section` |
| `sd-sec-head` | `stats-detail__head` |
| `sd-readout` | `stats-detail__readout` |
| `sd-plot` | `stats-detail__plot` |
| `sd-gl` | `stats-detail__gridline` |
| `sd-bars` | `stats-detail__bars` |
| `sd-bar` | `stats-detail__bar` |
| `sd-insights` | `stats-detail__insights` |
| `sd-people` | `stats-detail__people` |
| `sd-rank` | `stats-detail__rank` |
| `sd-pava` | `stats-detail__avatar` |
| `sd-pname` | `stats-detail__name` |
| `sd-pbar` | `stats-detail__bar-track` |
| `sd-pcount` | `stats-detail__count` |
| `sd-pshare` | `stats-detail__share` |
| `sd-media-bar` | `stats-detail__media-bar` |
| `sd-media-legend` | `stats-detail__media-legend` |
| `m-photo` | `media-photo` |
| `m-sticker` | `media-sticker` |
| `m-gif` | `media-gif` |
| `is-sel` | `is-selected` |

### галерея

| Було | Стало |
|---|---|
| `gallery-card` | `gallery` |
| `gal` | `gallery__grid` |
| `g` | `gallery__item` |
| `gt` | `gallery__caption` |
| `gp` | `gallery__badge` |

### картки ігор на головній

| Було | Стало |
|---|---|
| `game-letters` | `game-card__letters` |
| `game-demo-bubble` | `game-card__bubble` |
| `game-demo-grid` | `game-card__grid` |
| `f` | `game-card__cell--letter` |
| `x` | `game-card__cell--blank` |
| `tp` | `tetro-logo__piece` |
| `tc` | `tetro-logo__cell` |
| `tb-i` | `tetro-logo__cell--i` |
| `tb-o` | `tetro-logo__cell--o` |
| `tb-t` | `tetro-logo__cell--t` |
| `tb-s` | `tetro-logo__cell--s` |
| `tb-z` | `tetro-logo__cell--z` |
| `tb-j` | `tetro-logo__cell--j` |
| `tb-l` | `tetro-logo__cell--l` |

### сторінки ігор: спільне

| Було | Стало |
|---|---|
| `wordle-page-view` | `game-page` |
| `quiz-page-view` | `game-page--quiz` |
| `crossword-page-view` | `game-page--crossword` |
| `tetris-page-view` | `game-page--tetris` |
| `wordle-page-head` | `game-head` |
| `game-title` | `game-head__title` |
| `game-subtitle` | `game-head__subtitle` |
| `wordle-layout-grid` | `game-page__layout` |
| `wordle-game-card` | `game-board` |
| `wordle-side-col` | `game-page__side` |
| `w-start` | `game-start` |
| `w-start-inner` | `game-start__inner` |
| `w-start-title` | `game-start__title` |
| `w-start-text` | `game-start__text` |
| `w-next-note` | `game-start__note` |
| `w-legend` | `game-legend` |
| `ht-dot` | `game-legend__dot` |
| `good` | `is-correct` |
| `hi` | `is-present` |
| `absent` | `is-absent` |
| `no-anim` | `is-instant` |
| `w-key` | `game-key` |

### Wordle

| Було | Стало |
|---|---|
| `w-row` | `wordle__row` |
| `w-tile` | `wordle__tile` |
| `w-kr` | `wordle__kb-row` |
| `w-kb` | `wordle__kb` |
| `w-grid` | `wordle__grid` |
| `w-msg` | `wordle__msg` |
| `w-board-wrap` | `wordle__board` |
| `w-ans-tiles` | `wordle__answer` |
| `w-ans-tile` | `wordle__answer-tile` |
| `w-pattern` | `wordle__pattern` |
| `w-pattern-row` | `wordle__pattern-row` |
| `a` | `is-absent` |
| `c` | `is-correct` |
| `p` | `is-present` |
| `fill` | `is-filled` |
| `wide` | `is-wide` |
| `won` | `is-won` |
| `lost` | `is-lost` |

### Тетріс

| Було | Стало |
|---|---|
| `t-wrap` | `tetris` |
| `t-col` | `tetris__col` |
| `t-hud` | `tetris__hud` |
| `t-stat` | `tetris__stat` |
| `t-lab` | `tetris__stat-label` |
| `t-val` | `tetris__stat-value` |
| `long` | `is-long` |
| `t-side` | `tetris__side` |
| `t-next` | `tetris__next` |
| `t-board` | `tetris__board` |
| `t-toast` | `tetris__toast` |
| `t-pause` | `tetris__pause` |
| `t-pause-title` | `tetris__pause-title` |
| `t-controls` | `tetris__controls` |
| `t-res-stats` | `tetris__result-stats` |
| `t-res-actions` | `tetris__result-actions` |
| `t-legend` | `game-legend--keys` |
| `t-caps` | `keycaps` |
| `t-cap` | `keycaps__cap` |
| `t-note` | `tetris__note` |
| `t-key` | `game-key--control` |
| `t-pb` | `game-key--pause` |
| `main` | `game-key--drop` |

### «Хто це сказав?»

| Було | Стало |
|---|---|
| `q-board-wrap` | `quiz__board` |
| `q-dots` | `quiz__dots` |
| `q-dot` | `quiz__dot` |
| `q-bubble` | `quiz__bubble` |
| `q-time` | `quiz__time` |
| `q-opts` | `quiz__options` |
| `q-opt` | `quiz__option` |
| `q-bar` | `quiz__actions` |
| `q-score` | `quiz__score` |
| `q-pattern` | `quiz__pattern` |
| `w` | `is-wrong` |
| `active` | `is-active` |
| `correct` | `is-correct` |
| `wrong` | `is-wrong` |
| `right` | `is-right` |

### Кросворд

| Було | Стало |
|---|---|
| `cw-progress` | `crossword__progress` |
| `cw-layout` | `crossword__layout` |
| `cwg-wrap` | `crossword__grid-wrap` |
| `cwg` | `crossword__grid` |
| `clues` | `crossword__clues` |
| `cl-h` | `crossword__clues-title` |
| `cw-cur` | `crossword__current` |
| `cw-tools` | `crossword__tools` |
| `cw-msg` | `crossword__msg` |
| `cell` | `crossword__cell` |
| `n` | `crossword__cell-num` |
| `hl` | `is-highlight` |
| `cur` | `is-cursor` |
| `bad` | `is-bad` |
| `ok` | `is-ok` |
| `rev` | `is-revealed` |
| `act` | `is-active` |
| `done` | `is-done` |

### сторінка новини

| Було | Стало |
|---|---|
| `article-view-host` | `article-host` |
| `article-nav-bar` | `article-nav` |
| `nav-pos` | `article-nav__pos` |
| `article-columns` | `article__columns` |
| `article-col` | `article__col` |
| `article-main-body` | `article__body` |
| `article-title` | `article__title` |
| `article-prose` | `article__prose` |
| `article-media-grid` | `article__media-grid` |
| `article-media-box` | `article__media` |
| `article-media-fit` | `article__media-fit` |
| `article-stickers` | `article__stickers` |
| `an-card` | `article-next__card` |
| `an-meta` | `article-next__meta` |
| `an-kicker` | `article-next__kicker` |
| `an-title` | `article-next__title` |
| `an-btn` | `article-next__btn` |
| `article-side-nav` | `article-side` |
| `also-read-card` | `also-card` |
| `also-read-nav` | `also-list` |
| `news-progress` | `read-progress` |
| `np-text` | `read-progress__text` |
| `np-bar` | `read-progress__bar` |
| `news-continue` | `also-card__continue` |
| `ai` | `also-link` |
| `ai-thumb` | `also-link__thumb` |
| `ai-body` | `also-link__body` |
| `ai-cat` | `also-link__cat` |
| `ait` | `also-link__title` |
| `ai-go` | `also-link__go` |
| `ph` | `is-placeholder` |

### модальне вікно

| Було | Стало |
|---|---|
| `app-modal` | `modal` |
| `modal-content-panel` | `modal__panel` |
| `modal-header` | `modal__header` |
| `modal-kicker` | `modal__kicker` |
| `modal-title` | `modal__title` |
| `modal-close-btn` | `modal__close` |
| `media-close` | `modal__close--media` |
| `modal-body` | `modal__body` |
| `modal-media-panel` | `modal__media` |
| `modal-nav-btn` | `modal__nav` |
| `prev` | `modal__nav--prev` |
| `next` | `modal__nav--next` |
| `modal-media-stage` | `modal__stage` |
| `modal-media-wrap` | `modal__wrap` |
| `modal-media-footer` | `modal__footer` |
| `modal-caption` | `modal__caption` |
| `modal-counter` | `modal__counter` |
| `media-mode` | `is-media` |
| `modal-open` | `is-modal-open` |

### стани, що вже відповідають стандарту

| Було | Стало |
|---|---|
