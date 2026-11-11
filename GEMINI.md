---
# PROJECT-SPECIFIC RULES: CHAT NEWSPAPER (HTML TEMPLATE & GENERATOR)

## 9. Single-File HTML & Base64 Navigation (Навигация без перегрузки контекста)
- The newspaper HTML files are self-contained and may include massive inline data:font/woff2;base64 @font-face blocks or inline SVGs.
- NEVER read lines containing base64 data.
- Before reading any .html file, ALWAYS run a search (grep -n) to find the exact line numbers of target CSS selectors, <style>, <body>, <script>, or specific section headers.
- Read ONLY targeted line ranges (100–250 lines at a time) around the element you need to fix.

## 10. Theme System & CSS Variables (Защита светлой и тёмной темы)
- The newspaper uses a dual-theme architecture controlled by data-theme="light" and data-theme="dark" on <html>, persisted via localStorage (gazeta-theme) and <meta name="theme-color" id="tc">.
- NEVER hardcode raw #hex or rgb() colors inside individual blocks or fixes if a CSS variable (var(--...)) exists.
- If a new color token is strictly necessary, define it in BOTH :root / [data-theme="light"] and [data-theme="dark"].
- Never remove or alter the inline <head> theme-initialization script (document.documentElement.classList.add("js")).

## 11. Newspaper Grid, Bento & Card Isolation (Изоляция правок вёрстки)
- The layout relies on multi-column newspaper grids, bento blocks, cards, and responsive @media breakpoints (viewport-fit=cover).
- When fixing a visual bug in one specific block/widget, NEVER modify global container rules (.grid, .card, body, column spans) unless explicitly asked to change the global design.
- Scope CSS fixes to the specific block class or modifier so neighboring newspaper sections do not shift, stretch, or overflow.
- Always check that grid-column, flex, min-width: 0, and overflow properties remain intact for both desktop multi-column and mobile single-column views.

## 12. Self-Contained Vanilla JS & Interactive Widgets (Автономность интерактивных блоков)
- The generated newspaper MUST work 100% standalone when opened locally in a browser (file://).
- NEVER introduce external JS/CSS libraries, CDN links, or build-step dependencies. Use pure Vanilla HTML, CSS, and ES6 JavaScript.
- NEVER rename or delete existing id, data-* attributes, or classes bound to JavaScript event listeners (spoilers, tabs, polls, charts, theme toggle).

## 13. Chat Content, Language & Template Placeholders (Сохранность текста и сленга чата)
- Keep all Ukrainian (lang="uk") and Russian text, chat nicknames, inside jokes, slang, quotes, and issue titles (e.g., "Газета Вісник Big Yeet 2") 100% verbatim.
- NEVER "autocorrect", stylistically rewrite, or censor user quotes or headings unless specifically asked to edit the text.
- When editing generator templates or Python scripts, strictly preserve all template placeholders, Jinja tags, or string formatting markers.

## 14. Git Worktree & File Discipline (Безопасность рабочих директорий и файлов)
- Do NOT run git checkout <branch> or git switch if the workspace uses git worktree (separate directories for main and dev). Work strictly inside the current directory.
- Do not create duplicate backup files (*_fixed.html, *_new.html) unless requested; edit the target file in place and verify via git diff.