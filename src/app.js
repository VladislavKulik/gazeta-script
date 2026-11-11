/* ================= СПІЛЬНЕ: декодування даних, збереження, розкладка клавіатури ================= */
function dec(s) { return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(s), function (c) { return c.charCodeAt(0); }))); }
function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k)); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }
function mkEl(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined && text !== null) e.textContent = text; return e; }
var UA_LETTERS = 'АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ';
var CODEMAP = {
  KeyQ: 'Й', KeyW: 'Ц', KeyE: 'У', KeyR: 'К', KeyT: 'Е', KeyY: 'Н', KeyU: 'Г', KeyI: 'Ш', KeyO: 'Щ', KeyP: 'З', BracketLeft: 'Х', BracketRight: 'Ї',
  KeyA: 'Ф', KeyS: 'І', KeyD: 'В', KeyF: 'А', KeyG: 'П', KeyH: 'Р', KeyJ: 'О', KeyK: 'Л', KeyL: 'Д', Semicolon: 'Ж', Quote: 'Є',
  KeyZ: 'Я', KeyX: 'Ч', KeyC: 'С', KeyV: 'М', KeyB: 'И', KeyN: 'Т', KeyM: 'Ь', Comma: 'Б', Period: 'Ю', Backslash: 'Ґ'
};
function letterOf(e) {
  var k = (e.key || '').toUpperCase();
  if (k.length === 1 && UA_LETTERS.indexOf(k) >= 0) return k;
  return CODEMAP[e.code] || '';
}
function copyText(txt, btn, doneLabel, label) {
  (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(function () {
    if (!btn) return;
    btn.textContent = doneLabel || 'Скопійовано!';
    setTimeout(function () { btn.textContent = label || 'Скопіювати результат'; }, 2000);
  }, function () { prompt('Скопіюй результат:', txt); });
}


/* ================= МЕДІА: підтягування обкладинок, пауза відео =================
   Анімовані (TGS) стікери бібліотеку Lottie не підвантажують — файл автономний; шаблон показує їх як емодзі. */
var REDUCE_MOTION = false;
try { REDUCE_MOTION = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { }

/* Один файл медіа — одна копія даних: на сторінках новин і в «Читайте також» файл береться з обкладинки на головній */
function hydrate(root) {
  root.querySelectorAll('[data-ref]').forEach(function (el) {
    var id = el.getAttribute('data-ref');
    var srcEl = document.querySelector('#view-main [data-mid="' + id + '"]');
    if (!srcEl) return;
    var src = (srcEl.getAttribute('src') || '').split('#')[0];
    if (el.tagName === 'VIDEO' && el.getAttribute('preload') === 'metadata') src += '#t=0.001';
    el.setAttribute('src', src);
    if (el.tagName === 'VIDEO' && srcEl.getAttribute('poster') && !el.getAttribute('poster')) el.setAttribute('poster', srcEl.getAttribute('poster'));
    el.removeAttribute('data-ref');
  });
}

/* Відео головної не грають, поки відкрита інша сторінка */
function setMainVideos(play) {
  document.querySelectorAll('#view-main video[autoplay]').forEach(function (v) {
    if (play && !REDUCE_MOTION) v.play().catch(function () { }); else v.pause();
  });
}


// ================= WORDLE GAME LOGIC (FOR REDESIGNED 2-COLUMN VIEW) =================
var STATUS_CLASS = { a: 'is-absent', c: 'is-correct', p: 'is-present' };   // коди scoreWordle → класи
var WORDLE_CFG = { ANS: '', L: 5, TRIES: 6, KEY: '', DATE: '', W: {}, UA: UA_LETTERS };

function loadWordleCfg() {
  var node = document.getElementById('wordleData');
  var W = {};
  try { W = dec(node.textContent.trim()); } catch (e) { }
  var id = node ? (node.dataset.id || '') : '';
  var m = /^(\d{4})-(\d\d)-(\d\d)$/.exec(id);
  WORDLE_CFG.W = W;
  WORDLE_CFG.ANS = String(W.word || '').toUpperCase();
  WORDLE_CFG.L = WORDLE_CFG.ANS.length || 5;
  WORDLE_CFG.KEY = 'gazeta-wordle-' + id;
  WORDLE_CFG.DATE = m ? m.slice(1).reverse().join('.') : id;
}

var wordleDictSet = null, wordleDictPending = false;

/* Пакований словник (data-fmt="fc-deflate"): слова відсортовано, кожне записане як «цифра = скільки літер
   збігається з попереднім» + хвіст; усе стиснуто deflate-raw і закодовано base64. Розпаковка асинхронна
   (DecompressionStream). Якщо браузер її не вміє, гра приймає будь-яке слово потрібної довжини. */
function unpackWordleDict(el) {
  if (typeof DecompressionStream === 'undefined') return;
  wordleDictPending = true;
  try {
    var bin = atob(el.textContent.trim()), u = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    new Response(new Blob([u]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).text().then(function (t) {
      var parts = t.split(/(\d)/), prev = '', set = wordleDictSet || new Set();
      for (var j = 1; j + 1 < parts.length; j += 2) { prev = prev.slice(0, +parts[j]) + parts[j + 1]; set.add(prev.toUpperCase()); }
      wordleDictSet = set;
    }).catch(function () { }).then(function () { wordleDictPending = false; });
  } catch (e) { wordleDictPending = false; }
}

function getWordleDict() {
  if (wordleDictPending) return null;
  if (wordleDictSet) return wordleDictSet;
  var dictEl = document.getElementById('wdict');
  if (dictEl && dictEl.textContent.trim()) {
    if (dictEl.getAttribute('data-fmt') === 'fc-deflate') { unpackWordleDict(dictEl); if (wordleDictPending) return null; }
    else wordleDictSet = new Set(dictEl.textContent.trim().toUpperCase().split(/\s+/));
  }
  var extra = WORDLE_CFG.W && WORDLE_CFG.W.dictionary;
  if (extra && extra.length) {
    if (!wordleDictSet) wordleDictSet = new Set();
    extra.forEach(function (x) { wordleDictSet.add(String(x).toUpperCase()); });
  }
  return wordleDictSet;
}

var wordleState = {
  guesses: [],
  curr: '',
  msg: '',
  over: false,
  won: false
};

var wordleKeyHandler = null;

function scoreWordle(g) {
  var ans = WORDLE_CFG.ANS, L = WORDLE_CFG.L;
  var res = Array(L).fill('a'), left = {};
  for (var i = 0; i < L; i++) {
    if (g[i] === ans[i]) res[i] = 'c';
    else left[ans[i]] = (left[ans[i]] || 0) + 1;
  }
  for (var i = 0; i < L; i++) {
    if (res[i] !== 'c' && left[g[i]]) {
      res[i] = 'p';
      left[g[i]]--;
    }
  }
  return res;
}

function initWordle() {
  var boardWrap = document.getElementById('wBoardWrap');
  if (!boardWrap) return;
  loadWordleCfg();
  getWordleDict();   // для пакованого словника — старт розпаковки одразу, до першого слова

  // Load state from localStorage
  var saved = null;
  try { saved = JSON.parse(localStorage.getItem(WORDLE_CFG.KEY)); } catch (e) { }
  var guesses = (saved && saved.guesses) || [];
  var won = guesses.length > 0 && guesses[guesses.length - 1] === WORDLE_CFG.ANS;
  var over = won || guesses.length >= WORDLE_CFG.TRIES;

  wordleState = {
    guesses: guesses,
    curr: '',
    msg: '',
    over: over,
    won: won,
    // Гра починається після натискання «Грати»; розпочату або завершену гру показуємо одразу
    started: guesses.length > 0 || over
  };

  setWordleStart(!wordleState.started);
  renderWordleDOM();
  var startBtn = document.getElementById('wStartBtn');
  if (startBtn) startBtn.onclick = function () {
    wordleState.started = true;
    setWordleStart(false);
  };

  // Attach keydown listener safely
  if (wordleKeyHandler) {
    document.removeEventListener('keydown', wordleKeyHandler);
    wordleKeyHandler = null;
  }
  wordleKeyHandler = function (e) {
    var wrap = document.getElementById('wBoardWrap');
    if (!wrap || !document.contains(wrap)) return;
    if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    var appModal = document.getElementById('appModal');
    if (appModal && appModal.open) return;

    if (!wordleState.started) return;

    if (e.key === 'Enter') {
      e.preventDefault();
      pressWordleKey('ENTER');
    } else if (e.key === 'Backspace') {
      e.preventDefault();
      pressWordleKey('BACK');
    } else {
      var l = letterOf(e);
      if (l) {
        e.preventDefault();
        pressWordleKey(l);
      }
    }
  };
  document.addEventListener('keydown', wordleKeyHandler);
}

function setWordleEnd(show, instant) {
  var end = document.getElementById('wEnd');
  var wrap = document.getElementById('wBoardWrap');
  if (!show && (!end || end.hidden)) return;
  if (end) { end.classList.toggle('is-instant', !!instant); end.hidden = !show; }
  if (wrap) {
    wrap.style.visibility = show ? 'hidden' : '';
    if (show) wrap.setAttribute('inert', ''); else wrap.removeAttribute('inert');
  }
}

function setWordleStart(show) {
  var start = document.getElementById('wStart');
  var wrap = document.getElementById('wBoardWrap');
  if (start) start.hidden = !show;
  if (wrap) {
    wrap.style.visibility = show ? 'hidden' : '';
    if (show) wrap.setAttribute('inert', ''); else wrap.removeAttribute('inert');
  }
}

function pressWordleKey(k) {
  if (wordleState.over || !wordleState.started) return;
  var L = WORDLE_CFG.L;
  if (k === 'BACK') {
    wordleState.curr = wordleState.curr.slice(0, -1);
    wordleState.msg = '';
  } else if (k === 'ENTER') {
    if (wordleState.curr.length < L) {
      wordleState.msg = 'Потрібно ' + L + (L < 5 ? ' літери' : ' літер');
      renderWordleDOM();
      return;
    }
    var D = getWordleDict();
    if (D && !D.has(wordleState.curr) && wordleState.curr !== WORDLE_CFG.ANS) {
      wordleState.msg = 'Такого слова немає у словнику';
      renderWordleDOM();
      return;
    }
    var newGuesses = wordleState.guesses.concat([wordleState.curr]);
    var won0 = wordleState.curr === WORDLE_CFG.ANS;
    store(WORDLE_CFG.KEY, { guesses: newGuesses, over: won0 || newGuesses.length >= WORDLE_CFG.TRIES, won: won0 });
    var won = wordleState.curr === WORDLE_CFG.ANS;
    var over = won || newGuesses.length >= WORDLE_CFG.TRIES;
    wordleState.guesses = newGuesses;
    wordleState.curr = '';
    wordleState.msg = '';
    wordleState.won = won;
    wordleState.over = over;
    wordleState.justFinished = over;
  } else if (wordleState.curr.length < L) {
    wordleState.curr += k;
    wordleState.msg = '';
  }
  renderWordleDOM();
}

function renderWordleDOM() {
  var grid = document.getElementById('wGrid');
  var msg = document.getElementById('wMsg');
  var kb = document.getElementById('wKb');
  var res = document.getElementById('wResult');
  if (!grid || !kb || !res) return;

  var L = WORDLE_CFG.L, TRIES = WORDLE_CFG.TRIES;
  var bestKeyScores = {};
  var rank = { a: 1, p: 2, c: 3 };

  // 1. Render Grid
  grid.innerHTML = '';
  for (var r = 0; r < TRIES; r++) {
    var rowEl = document.createElement('div');
    rowEl.className = 'wordle__row';
    var g = wordleState.guesses[r];
    var sc = g ? scoreWordle(g) : null;

    for (var c = 0; c < L; c++) {
      var tileEl = document.createElement('div');
      var ch = g ? g[c] : ((r === wordleState.guesses.length && !wordleState.over) ? (wordleState.curr[c] || '') : '');
      var statusClass = sc ? (' ' + STATUS_CLASS[sc[c]]) : (ch ? ' is-filled' : '');
      tileEl.className = 'wordle__tile' + statusClass;
      tileEl.textContent = ch;
      rowEl.appendChild(tileEl);

      if (sc && (!bestKeyScores[ch] || rank[sc[c]] > rank[bestKeyScores[ch]])) {
        bestKeyScores[ch] = sc[c];
      }
    }
    grid.appendChild(rowEl);
  }

  // 2. Render Message
  if (msg) msg.textContent = wordleState.msg;

  // 3. Render Keyboard / Result
  if (!wordleState.over) {
    kb.style.display = 'flex';
    setWordleEnd(false);

    var KB_ROWS = [
      ['Й', 'Ц', 'У', 'К', 'Е', 'Н', 'Г', 'Ш', 'Щ', 'З', 'Х', 'Ї'],
      ['Ф', 'І', 'В', 'А', 'П', 'Р', 'О', 'Л', 'Д', 'Ж', 'Є'],
      ['ENTER', 'Я', 'Ч', 'С', 'М', 'И', 'Т', 'Ь', 'Б', 'Ю', 'Ґ', 'BACK']
    ];

    kb.innerHTML = '';
    KB_ROWS.forEach(function (row) {
      var rDiv = document.createElement('div');
      rDiv.className = 'wordle__kb-row';
      row.forEach(function (k) {
        var btn = document.createElement('button');
        var wide = (k === 'ENTER' || k === 'BACK');
        var st = bestKeyScores[k] || '';
        btn.type = 'button';
        btn.className = 'game-key' + (wide ? ' is-wide' : '') + (st ? (' ' + STATUS_CLASS[st]) : '');
        btn.textContent = k === 'ENTER' ? '⏎' : (k === 'BACK' ? '⌫' : k);
        btn.setAttribute('aria-label', k === 'ENTER' ? 'Ввести' : (k === 'BACK' ? 'Стерти' : k));
        btn.onclick = function () { pressWordleKey(k); };
        rDiv.appendChild(btn);
      });
      kb.appendChild(rDiv);
    });
  } else {
    kb.style.display = 'none';
    // щойно завершена гра: спершу видно останній ряд, за секунду — екран результату
    var endEl = document.getElementById('wEnd');
    if (wordleState.justFinished) {
      wordleState.justFinished = false;
      setTimeout(function () {
        if (document.getElementById('wEnd') === endEl && wordleState.over) setWordleEnd(true);
      }, 1000);
    } else {
      setWordleEnd(true, true);
    }

    var n = wordleState.guesses.length;
    var ansTilesEl = document.getElementById('wAnsTiles');
    ansTilesEl.innerHTML = '';
    WORDLE_CFG.ANS.split('').forEach(function (ch) {
      var t = document.createElement('div');
      t.className = 'wordle__answer-tile ' + (wordleState.won ? 'is-won' : 'is-lost');
      t.textContent = ch;
      ansTilesEl.appendChild(t);
    });

    document.getElementById('wResultTitle').textContent = wordleState.won ? ('🎉 Вгадано з ' + n + '-ї спроби!') : 'Цього разу не вийшло';

    var whyEl = document.getElementById('wWhyText');
    if (whyEl) {
      var Wd = WORDLE_CFG.W || {}, cnt = Wd.count;
      var fm = cnt % 10 === 1 && cnt % 100 !== 11 ? 'раз' : (cnt % 10 >= 2 && cnt % 10 <= 4 && (cnt % 100 < 12 || cnt % 100 > 14) ? 'рази' : 'разів');
      whyEl.textContent = Wd.why ? (Wd.why + (cnt ? ' (у чаті — ' + cnt + ' ' + fm + ')' : '')) : '';
      whyEl.hidden = !whyEl.textContent;
    }
    ansTilesEl.setAttribute('aria-label', 'Слово дня: ' + WORDLE_CFG.ANS);

    var patEl = document.getElementById('wPattern');
    patEl.innerHTML = '';
    wordleState.guesses.forEach(function (g) {
      var pRow = document.createElement('div');
      pRow.className = 'wordle__pattern-row';
      scoreWordle(g).forEach(function (x) {
        var sp = document.createElement('span');
        sp.style.background = x === 'c' ? 'var(--good)' : (x === 'p' ? 'var(--hi)' : 'var(--absent)');
        pRow.appendChild(sp);
      });
      patEl.appendChild(pRow);
    });

    var copyBtn = document.getElementById('wCopyBtn');
    copyBtn.onclick = function () {
      var txt = 'Wordle ' + WORDLE_CFG.DATE + ' ' + (wordleState.won ? n : 'X') + '/' + WORDLE_CFG.TRIES + '\n' +
        wordleState.guesses.map(function (g) {
          return scoreWordle(g).map(function (x) { return x === 'c' ? '🟪' : (x === 'p' ? '🟨' : '⬛'); }).join('');
        }).join('\n');
      copyText(txt, copyBtn);
    };
  }
}


// ================= TETRIS (ГРА В РОЗДІЛІ «ІГРИ») =================
// Частина 1 — рушій (чиста логіка без DOM). Частина 2 — відображення й керування.
var TETRIS_CFG = {
  COLS: 10, ROWS: 20,
  PER_LEVEL: 10,     // ліній до наступного рівня
  LOCK_MS: 500,      // затримка перед фіксацією фігури на опорі
  MAX_RESETS: 15,    // скільки разів рух/поворот можуть її продовжити
  CLEAR_MS: 240,     // мигання повних рядків
  BEST_KEY: 'gazeta-tetris-best'
};
var TETRIS_TYPES = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];
var TETRIS_SHAPES = {
  I: [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]],
  O: [[1, 1], [1, 1]],
  T: [[0, 1, 0], [1, 1, 1], [0, 0, 0]],
  S: [[0, 1, 1], [1, 1, 0], [0, 0, 0]],
  Z: [[1, 1, 0], [0, 1, 1], [0, 0, 0]],
  J: [[1, 0, 0], [1, 1, 1], [0, 0, 0]],
  L: [[0, 0, 1], [1, 1, 1], [0, 0, 0]]
};
var TETRIS_LINE_POINTS = [0, 100, 300, 500, 800];

function tRotateM(m, dir) {
  var n = m.length, r = [], i, j;
  for (i = 0; i < n; i++) { r.push([]); for (j = 0; j < n; j++) r[i].push(0); }
  for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
    if (dir > 0) r[j][n - 1 - i] = m[i][j]; else r[n - 1 - j][i] = m[i][j];
  }
  return r;
}

function tCollide(board, m, x, y) {
  var n = m.length, i, j, bx, by;
  for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
    if (!m[i][j]) continue;
    bx = x + j; by = y + i;
    if (bx < 0 || bx >= TETRIS_CFG.COLS || by >= TETRIS_CFG.ROWS) return true;
    if (by >= 0 && board[by][bx]) return true;
  }
  return false;
}

function tNextType(S) {
  if (!S.bag.length) {
    var b = TETRIS_TYPES.slice(), i, j, t;
    for (i = b.length - 1; i > 0; i--) { j = Math.floor(Math.random() * (i + 1)); t = b[i]; b[i] = b[j]; b[j] = t; }
    S.bag = b;
  }
  return S.bag.pop();
}

function tMakePiece(type) {
  var m = TETRIS_SHAPES[type].map(function (row) { return row.slice(); });
  var top = 0;
  while (top < m.length && !m[top].some(function (v) { return v; })) top++;
  return { t: type, m: m, x: Math.floor((TETRIS_CFG.COLS - m.length) / 2), y: -top };
}

function tInterval(level) {
  return Math.max(60, Math.round(800 * Math.pow(0.85, level - 1)));
}

function tSpawn(S) {
  S.cur = S.next;
  S.next = tMakePiece(tNextType(S));
  S.dropAcc = 0; S.lockAcc = 0; S.lockResets = 0;
  if (tCollide(S.board, S.cur.m, S.cur.x, S.cur.y)) S.status = 'over';
}

function tNewState(best) {
  var S = {
    board: [], bag: [], cur: null, next: null,
    score: 0, lines: 0, level: 1, best: best || 0,
    status: 'ready',              // ready | playing | paused | clearing | over
    dropAcc: 0, lockAcc: 0, lockResets: 0,
    clearRows: [], clearT: 0, clearMs: TETRIS_CFG.CLEAR_MS,
    bv: 0, event: null
  };
  for (var r = 0; r < TETRIS_CFG.ROWS; r++) {
    var row = [];
    for (var c = 0; c < TETRIS_CFG.COLS; c++) row.push(0);
    S.board.push(row);
  }
  S.next = tMakePiece(tNextType(S));
  tSpawn(S);
  return S;
}

function tOnGround(S) {
  return tCollide(S.board, S.cur.m, S.cur.x, S.cur.y + 1);
}

// після руху/повороту на опорі таймер фіксації починається знову (але не безкінечно)
function tAfterMove(S) {
  if (tOnGround(S)) {
    if (S.lockResets < TETRIS_CFG.MAX_RESETS) { S.lockResets++; S.lockAcc = 0; }
  } else {
    S.lockAcc = 0;
  }
}

function tTryMove(S, dx, dy) {
  if (tCollide(S.board, S.cur.m, S.cur.x + dx, S.cur.y + dy)) return false;
  S.cur.x += dx; S.cur.y += dy;
  return true;
}

function tTryRotate(S, dir) {
  var m = tRotateM(S.cur.m, dir);
  var kicks = [[0, 0], [-1, 0], [1, 0], [-2, 0], [2, 0], [0, -1], [-1, -1], [1, -1]];
  for (var k = 0; k < kicks.length; k++) {
    var nx = S.cur.x + kicks[k][0], ny = S.cur.y + kicks[k][1];
    if (!tCollide(S.board, m, nx, ny)) { S.cur.m = m; S.cur.x = nx; S.cur.y = ny; return true; }
  }
  return false;
}

function tSoftDrop(S) {
  if (!tTryMove(S, 0, 1)) return false;
  S.score += 1; S.dropAcc = 0;
  return true;
}

function tGhostY(S) {
  var y = S.cur.y;
  while (!tCollide(S.board, S.cur.m, S.cur.x, y + 1)) y++;
  return y;
}

function tHardDrop(S) {
  var d = 0;
  while (tTryMove(S, 0, 1)) d++;
  S.score += d * 2;
  tLock(S);
}

function tLock(S) {
  var m = S.cur.m, n = m.length, i, j, by, bx, out = false;
  for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
    if (!m[i][j]) continue;
    by = S.cur.y + i; bx = S.cur.x + j;
    if (by < 0) out = true; else S.board[by][bx] = S.cur.t;
  }
  S.cur = null;
  S.bv = (S.bv | 0) + 1;                    // версія поля — для перемальовування лише коли воно змінилось
  if (out) { S.status = 'over'; return; }   // фігура зафіксувалась над полем
  var full = [];
  for (i = 0; i < TETRIS_CFG.ROWS; i++) {
    if (S.board[i].every(function (v) { return v; })) full.push(i);
  }
  if (full.length) { S.clearRows = full; S.clearT = 0; S.status = 'clearing'; }
  else tSpawn(S);
}

function tFinishClear(S) {
  var rows = S.clearRows, n = rows.length, i;
  for (i = rows.length - 1; i >= 0; i--) S.board.splice(rows[i], 1);
  for (i = 0; i < n; i++) {
    var row = [];
    for (var c = 0; c < TETRIS_CFG.COLS; c++) row.push(0);
    S.board.unshift(row);
  }
  var pts = TETRIS_LINE_POINTS[n] * S.level, oldLevel = S.level;
  S.lines += n;
  S.score += pts;
  S.level = Math.floor(S.lines / TETRIS_CFG.PER_LEVEL) + 1;
  S.event = { n: n, pts: pts, level: S.level > oldLevel ? S.level : 0 };
  S.clearRows = []; S.clearT = 0;
  S.bv = (S.bv | 0) + 1;
  S.status = 'playing';
  tSpawn(S);
}

function tUpdate(S, dt) {
  if (S.status === 'clearing') {
    S.clearT += dt;
    if (S.clearT >= S.clearMs) tFinishClear(S);
    return;
  }
  if (S.status !== 'playing' || !S.cur) return;
  var interval = tInterval(S.level);
  if (tOnGround(S)) {
    S.lockAcc += dt;
    if (S.lockAcc >= TETRIS_CFG.LOCK_MS) tLock(S);
  } else {
    S.lockAcc = 0;
    S.dropAcc += dt;
    while (S.dropAcc >= interval) {
      S.dropAcc -= interval;
      if (!tTryMove(S, 0, 1)) break;
    }
    if (tOnGround(S)) S.dropAcc = 0;
  }
}
// @tetris-engine-end

// ---------- Частина 2 — відображення й керування ----------
var tetrisState = null;
var tetrisKeyDown = null, tetrisKeyUp = null, tetrisVis = null;
var tetrisRepT = null, tetrisRepI = null;

var tFmtNF = null;
try { tFmtNF = new Intl.NumberFormat('uk-UA'); } catch (e) { }
function tFmt(n) { return tFmtNF ? tFmtNF.format(n) : String(n); }
function tPlural(n, f) {
  var a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return f[2];
  if (b > 1 && b < 5) return f[1];
  if (b === 1) return f[0];
  return f[2];
}
function tReadBest() {
  var v = 0;
  try { v = parseInt(localStorage.getItem(TETRIS_CFG.BEST_KEY), 10) || 0; } catch (e) { }
  return v;
}
function tSaveBest(v) {
  try { localStorage.setItem(TETRIS_CFG.BEST_KEY, String(v)); } catch (e) { }
}

function tetrisColors() {
  var cs = getComputedStyle(document.documentElement);
  function v(n) { return cs.getPropertyValue(n).trim(); }
  var dark = document.documentElement.dataset.theme === 'dark';
  return {
    theme: document.documentElement.dataset.theme || '',
    card: v('--card'), pill: v('--pill'), hi: v('--hi'),
    piece: {
      I: '#22b8c4', O: v('--hi'), T: v('--accent'),
      S: dark ? '#2ba46c' : v('--good'),
      Z: '#e5484d', J: '#d946a8', L: '#f08a24'
    }
  };
}

// одна заокруглена клітинка (окремий підшлях — щоб малювати багато клітинок одним fill)
function tRRp(ctx, x, y, w, h, r) {
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function tRR(ctx, x, y, w, h, r) { ctx.beginPath(); tRRp(ctx, x, y, w, h, r); }

// Нерухома частина поля (порожні клітинки + зафіксовані фігури) малюється в окремий шар
// лише коли поле змінилось, а в кожному кадрі — лише готовий шар і фігура, що падає.
function tetrisBuildLayer(S, size) {
  var C = S.colors, CELL = 40, k = size / 400, r, c, t;
  var layer = S.layer || (S.layer = document.createElement('canvas'));
  if (layer.width !== size || layer.height !== size * 2) { layer.width = size; layer.height = size * 2; }
  var lc = layer.getContext('2d');
  lc.setTransform(k, 0, 0, k, 0, 0);
  lc.fillStyle = C.card;
  lc.fillRect(0, 0, 400, 800);
  lc.fillStyle = C.pill;                       // всі порожні клітинки — одним шляхом
  lc.beginPath();
  for (r = 0; r < TETRIS_CFG.ROWS; r++) for (c = 0; c < TETRIS_CFG.COLS; c++) tRRp(lc, c * CELL + 2, r * CELL + 2, CELL - 4, CELL - 4, 8);
  lc.fill();
  var groups = {};                             // зафіксовані — по одному шляху на колір
  for (r = 0; r < TETRIS_CFG.ROWS; r++) for (c = 0; c < TETRIS_CFG.COLS; c++) {
    t = S.board[r][c];
    if (t) (groups[t] || (groups[t] = [])).push(r * TETRIS_CFG.COLS + c);
  }
  Object.keys(groups).forEach(function (type) {
    lc.fillStyle = C.piece[type];
    lc.beginPath();
    groups[type].forEach(function (i) {
      tRRp(lc, (i % TETRIS_CFG.COLS) * CELL + 2, Math.floor(i / TETRIS_CFG.COLS) * CELL + 2, CELL - 4, CELL - 4, 8);
    });
    lc.fill();
  });
}

function tetrisDraw() {
  var S = tetrisState;
  if (!S || !S.ctx) return;
  var theme = document.documentElement.dataset.theme || '';
  var themeChanged = !S.colors || S.colors.theme !== theme;
  if (themeChanged) S.colors = tetrisColors();
  var cv = S.canvas;

  // розмір буфера = CSS-ширина × DPR, але не більше 2× і не більше 600 px:
  // на телефонах з DPR 3 це майже вдвічі менше пікселів, а різниці на око немає
  var cw = S.ro ? S.cw : cv.clientWidth;
  var size = Math.max(300, Math.min(600, Math.round((cw || 300) * Math.min(window.devicePixelRatio || 1, 2))));
  var resized = cv.width !== size;
  if (resized) { cv.width = size; cv.height = size * 2; }

  var cur = S.cur;
  var phase = S.status === 'clearing' ? (Math.floor(S.clearT / 60) % 2) : -1;
  var d = S.drawn || (S.drawn = {});
  var boardDirty = themeChanged || resized || !S.layer || d.bv !== S.bv;
  var changed = boardDirty || d.status !== S.status || d.cur !== cur || d.phase !== phase ||
    (cur && (d.x !== cur.x || d.y !== cur.y || d.m !== cur.m));
  var nextChanged = themeChanged || d.next !== S.next;
  if (!changed && !nextChanged) return;      // нічого не змінилось — нічого й не малюємо

  var C = S.colors;
  if (changed) {
    var ctx = S.ctx, CELL = 40, k = size / 400, i, j, c;
    if (boardDirty) tetrisBuildLayer(S, size);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(S.layer, 0, 0);
    ctx.setTransform(k, 0, 0, k, 0, 0);

    // повні рядки блимають жовтим
    if (S.status === 'clearing') {
      ctx.fillStyle = phase === 0 ? C.hi : C.card;
      ctx.beginPath();
      S.clearRows.forEach(function (row) {
        for (c = 0; c < TETRIS_CFG.COLS; c++) tRRp(ctx, c * CELL + 2, row * CELL + 2, CELL - 4, CELL - 4, 8);
      });
      ctx.fill();
    }
    // тінь і поточна фігура
    if (cur && (S.status === 'playing' || S.status === 'paused')) {
      var gy = tGhostY(S), m = cur.m, n = m.length;
      if (gy !== cur.y) {
        ctx.lineWidth = 3;
        ctx.strokeStyle = C.piece[cur.t];
        ctx.globalAlpha = 0.45;
        ctx.beginPath();
        for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
          if (!m[i][j] || gy + i < 0) continue;
          tRRp(ctx, (cur.x + j) * CELL + 3.5, (gy + i) * CELL + 3.5, CELL - 7, CELL - 7, 7);
        }
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      ctx.fillStyle = C.piece[cur.t];
      ctx.beginPath();
      for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
        if (!m[i][j] || cur.y + i < 0) continue;
        tRRp(ctx, (cur.x + j) * CELL + 2, (cur.y + i) * CELL + 2, CELL - 4, CELL - 4, 8);
      }
      ctx.fill();
    }
    // кінець гри: поле приглушується
    if (S.status === 'over') {
      ctx.globalAlpha = 0.55;
      ctx.fillStyle = C.card;
      ctx.fillRect(0, 0, 400, 800);
      ctx.globalAlpha = 1;
    }
    d.bv = S.bv; d.status = S.status; d.cur = cur; d.phase = phase;
    if (cur) { d.x = cur.x; d.y = cur.y; d.m = cur.m; }
  }
  if (nextChanged) { tetrisDrawNext(C); d.next = S.next; }
}

function tetrisDrawNext(C) {
  var S = tetrisState, nc = S.nctx;
  if (!nc || !S.next) return;
  var cell = 24, W = 112, m = S.next.m, n = m.length, i, j;
  nc.clearRect(0, 0, W, W);
  var minR = 9, maxR = -1, minC = 9, maxC = -1;
  for (i = 0; i < n; i++) for (j = 0; j < n; j++) if (m[i][j]) {
    minR = Math.min(minR, i); maxR = Math.max(maxR, i); minC = Math.min(minC, j); maxC = Math.max(maxC, j);
  }
  var ox = (W - (maxC - minC + 1) * cell) / 2, oy = (W - (maxR - minR + 1) * cell) / 2;
  nc.fillStyle = C.piece[S.next.t];
  nc.beginPath();
  for (i = minR; i <= maxR; i++) for (j = minC; j <= maxC; j++) {
    if (m[i][j]) tRRp(nc, ox + (j - minC) * cell + 1.5, oy + (i - minR) * cell + 1.5, cell - 3, cell - 3, 6);
  }
  nc.fill();
}

function tetrisSay(text, ms) {
  var el = document.getElementById('tMsg');
  if (el) el.textContent = text;
  if (tetrisState) tetrisState.msgUntil = ms ? performance.now() + ms : 0;
}

function tetrisSync() {
  var S = tetrisState;
  if (!S) return;
  var h = S.hud || (S.hud = {});
  function set(id, raw, fmt) {
    if (h[id] === raw) return;
    h[id] = raw;
    var el = document.getElementById(id);
    if (!el) return;
    var v = fmt ? tFmt(raw) : String(raw);
    el.textContent = v;
    el.classList.toggle('is-long', v.length >= 6);   // довгі числа трохи менші, щоб не обрізались
  }
  set('tScore', S.score, true);
  set('tBest', Math.max(S.best, S.score), true);
  set('tLevel', S.level, false);
  set('tLines', S.lines, false);

  if (S.event) {
    var ev = S.event;
    S.event = null;
    var txt = (ev.n === 4 ? 'Тетріс! ' : '') + '+' + tFmt(ev.pts);
    if (ev.level) txt += ' · Рівень ' + ev.level;
    tetrisSay(txt, 2200);
  } else if (S.msgUntil && performance.now() > S.msgUntil) {
    tetrisSay('', 0);
  }
  if (S.status === 'over' && !S.overHandled) tetrisGameOver();
}

function tetrisFrame(ts) {
  var S = tetrisState;
  if (!S || !S.canvas || !document.body.contains(S.canvas)) { tetrisCleanup(); return; }
  var dt = Math.min(100, ts - (S.last || ts));
  S.last = ts;
  if (S.status === 'playing' || S.status === 'clearing') tUpdate(S, dt);
  tetrisSync();
  tetrisDraw();
  S.raf = requestAnimationFrame(tetrisFrame);
}

function tetrisCleanup() {
  tetrisStopRepeat();
  if (tetrisState && tetrisState.ro) tetrisState.ro.disconnect();
  if (tetrisState && tetrisState.raf) cancelAnimationFrame(tetrisState.raf);
  if (tetrisKeyDown) { document.removeEventListener('keydown', tetrisKeyDown); tetrisKeyDown = null; }
  if (tetrisKeyUp) { document.removeEventListener('keyup', tetrisKeyUp); tetrisKeyUp = null; }
  if (tetrisVis) { document.removeEventListener('visibilitychange', tetrisVis); tetrisVis = null; }
  tetrisState = null;
}

// ----- дії гравця (клавіатура, кнопки, свайпи) -----
function tetrisAct(a) {
  var S = tetrisState;
  if (!S || S.status !== 'playing' || !S.cur) return;
  var ok;
  if (a === 'left') { ok = tTryMove(S, -1, 0); if (ok) tAfterMove(S); }
  else if (a === 'right') { ok = tTryMove(S, 1, 0); if (ok) tAfterMove(S); }
  else if (a === 'rotate') { ok = tTryRotate(S, 1); if (ok) tAfterMove(S); }
  else if (a === 'rotateccw') { ok = tTryRotate(S, -1); if (ok) tAfterMove(S); }
  else if (a === 'down') { tSoftDrop(S); }
  else if (a === 'drop') { tHardDrop(S); }
  tetrisSync();
}

function tetrisStopRepeat() {
  if (tetrisRepT) { clearTimeout(tetrisRepT); tetrisRepT = null; }
  if (tetrisRepI) { clearInterval(tetrisRepI); tetrisRepI = null; }
}
function tetrisStartRepeat(a) {
  tetrisStopRepeat();
  tetrisRepT = setTimeout(function () {
    tetrisRepI = setInterval(function () { tetrisAct(a); }, a === 'down' ? 45 : 70);
  }, 180);
}

function tetrisSetPaused(p) {
  var S = tetrisState;
  if (!S) return;
  if (p && S.status === 'playing') {
    S.status = 'paused';
    tetrisStopRepeat();
  } else if (!p && S.status === 'paused') {
    S.status = 'playing';
    S.last = performance.now();
  } else return;
  var ov = document.getElementById('tPause');
  if (ov) ov.hidden = !p;
  var btn = document.getElementById(p ? 'tResume' : 'tPauseBtn');
  if (p && btn) btn.focus({ preventScroll: true });
}

function setTetrisStart(show) {
  var start = document.getElementById('tStart');
  var wrap = document.getElementById('tBoardWrap');
  if (start) start.hidden = !show;
  if (wrap) {
    wrap.style.visibility = show ? 'hidden' : '';
    if (show) wrap.setAttribute('inert', ''); else wrap.removeAttribute('inert');
  }
}

function tetrisBegin() {
  var S = tetrisState;
  if (!S || S.status !== 'ready') return;
  S.status = 'playing';
  S.last = performance.now();
  setTetrisStart(false);
  // фокус лишаємо на сторінці, а не на кнопці, щоб пробіл не «натискав» її
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
}

function tetrisRestart() {
  var old = tetrisState;
  if (!old) return;
  var S = tNewState(old.best);
  S.canvas = old.canvas; S.ctx = old.ctx; S.nctx = old.nctx; S.colors = old.colors; S.raf = old.raf;
  S.ro = old.ro; S.cw = old.cw; S.layer = old.layer;
  S.clearMs = old.clearMs; S.last = performance.now(); S.hud = {};
  S.status = 'playing';
  tetrisState = S;
  setTetrisEnd(false);
  document.getElementById('tPauseBtn').disabled = false;
  tetrisSay('', 0);
}

// екран результату — той самий оверлей, що й стартовий (.w-start)
function setTetrisEnd(show) {
  var end = document.getElementById('tEnd');
  var wrap = document.getElementById('tBoardWrap');
  if (end) end.hidden = !show;
  if (wrap) {
    wrap.style.visibility = show ? 'hidden' : '';
    if (show) wrap.setAttribute('inert', ''); else wrap.removeAttribute('inert');
  }
}

function tetrisGameOver() {
  var S = tetrisState;
  if (!S) return;
  S.overHandled = true;
  tetrisStopRepeat();
  var rec = S.score > S.best && S.score > 0;
  var prevBest = S.best;
  if (S.score > S.best) { S.best = S.score; tSaveBest(S.best); }

  document.getElementById('tPauseBtn').disabled = true;
  document.getElementById('tResTitle').textContent = rec ? '🎉 Новий рекорд!' : 'Гру завершено';
  document.getElementById('tResScore').textContent = tFmt(S.score);
  document.getElementById('tResLines').textContent = String(S.lines);
  document.getElementById('tResLevel').textContent = String(S.level);
  var txt;
  if (rec) txt = 'Це найкращий результат на цьому пристрої. Спробуєш побити ще раз?';
  else if (S.score >= prevBest && S.score > 0) txt = 'Це ваш рекорд — рівно стільки ж очок.';
  else if (prevBest > 0) { var d = prevBest - S.score; txt = 'До рекорду бракує ' + tFmt(d) + ' ' + tPlural(d, ['очка', 'очок', 'очок']) + '. Ще одна спроба?'; }
  else txt = 'Склади більше рядків — і рекорд буде твій.';
  document.getElementById('tResText').textContent = txt;
  tetrisSay('', 0);

  var copyBtn = document.getElementById('tCopyBtn');
  copyBtn.textContent = 'Скопіювати результат';
  copyBtn.onclick = function () {
    var st = tetrisState || S;
    var out = 'Тетріс 🟪🟨🟩\nРахунок: ' + tFmt(st.score) + '\nЛінії: ' + st.lines + ' · Рівень: ' + st.level;
    (navigator.clipboard ? navigator.clipboard.writeText(out) : Promise.reject()).then(function () {
      copyBtn.textContent = 'Скопійовано!';
      setTimeout(function () { copyBtn.textContent = 'Скопіювати результат'; }, 2000);
    }, function () {
      prompt('Скопіюй результат:', out);
    });
  };
  document.getElementById('tRetryBtn').onclick = tetrisRestart;
  // коротка пауза, щоб побачити приглушене поле, а потім — екран результату (як у Wordle)
  tetrisSay('', 0);
  setTimeout(function () {
    if (tetrisState === S && S.status === 'over') setTetrisEnd(true);
  }, 800);
}

function tetrisBindControls() {
  var btns = document.querySelectorAll('#tControls [data-act]');
  Array.prototype.forEach.call(btns, function (el) {
    var a = el.getAttribute('data-act');
    var rep = a === 'left' || a === 'right' || a === 'down';
    // не даємо кнопці забрати фокус — інакше пробіл «натискатиме» її
    el.addEventListener('mousedown', function (e) { e.preventDefault(); });
    el.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    el.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      e.preventDefault();
      tetrisAct(a);
      if (rep) tetrisStartRepeat(a);
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) {
      el.addEventListener(ev, tetrisStopRepeat);
    });
    // click з detail=0 — це активація з клавіатури (Tab → Enter/Пробіл)
    el.addEventListener('click', function (e) { if (e.detail === 0) tetrisAct(a); });
  });
}

function tetrisBindSwipe(cv) {
  var g = null;
  cv.addEventListener('pointerdown', function (e) {
    var S = tetrisState;
    if (!S || S.status !== 'playing') return;
    e.preventDefault();
    try { cv.setPointerCapture(e.pointerId); } catch (err) { }
    g = { id: e.pointerId, sx: e.clientX, sy: e.clientY, px: e.clientX, py: e.clientY, ax: 0, ay: 0, t: performance.now(), moved: false };
  });
  cv.addEventListener('pointermove', function (e) {
    if (!g || e.pointerId !== g.id) return;
    var cell = cv.clientWidth / TETRIS_CFG.COLS;
    g.ax += e.clientX - g.px;
    g.ay = Math.max(0, g.ay + (e.clientY - g.py));
    g.px = e.clientX; g.py = e.clientY;
    while (g.ax >= cell) { tetrisAct('right'); g.ax -= cell; g.moved = true; }
    while (g.ax <= -cell) { tetrisAct('left'); g.ax += cell; g.moved = true; }
    while (g.ay >= cell) { tetrisAct('down'); g.ay -= cell; g.moved = true; }
  });
  function end(e) {
    if (!g || e.pointerId !== g.id) return;
    var cell = cv.clientWidth / TETRIS_CFG.COLS;
    var dt = Math.max(1, performance.now() - g.t), dy = g.py - g.sy, dx = Math.abs(g.px - g.sx);
    if (e.type === 'pointerup') {
      if (!g.moved && dt < 280 && Math.abs(dy) < 10 && dx < 10) tetrisAct('rotate');      // дотик — поворот
      else if (dy > cell * 2.5 && dy / dt > 0.9) tetrisAct('drop');                        // різкий свайп вниз — скинути
    }
    g = null;
  }
  cv.addEventListener('pointerup', end);
  cv.addEventListener('pointercancel', end);
}

function initTetris() {
  var cv = document.getElementById('tCanvas');
  if (!cv) return;
  tetrisCleanup();

  var S = tNewState(tReadBest());
  S.canvas = cv;
  S.ctx = cv.getContext('2d', { alpha: false });   // непрозоре полотно швидше компонується
  S.cw = cv.clientWidth;
  if (window.ResizeObserver) {
    S.ro = new ResizeObserver(function (es) { S.cw = es[0].contentRect.width; });
    S.ro.observe(cv);
  }
  S.nctx = document.getElementById('tNext').getContext('2d');
  S.hud = {};
  try { if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) S.clearMs = 0; } catch (e) { }
  tetrisState = S;

  // стартовий екран з правилами — гра починається лише після «Грати»
  setTetrisStart(true);
  document.getElementById('tStartBtn').onclick = tetrisBegin;
  document.getElementById('tPauseBtn').onclick = function () { tetrisSetPaused(true); };
  document.getElementById('tResume').onclick = function () { tetrisSetPaused(false); };
  tetrisBindControls();
  tetrisBindSwipe(cv);
  tetrisSync();
  tetrisDraw();

  tetrisKeyDown = function (e) {
    var St = tetrisState;
    if (!St || !document.body.contains(St.canvas)) return;
    if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    var am = document.getElementById('appModal');
    if (am && am.open) return;
    var code = e.code;
    if (code === 'KeyP' || code === 'Escape') {
      if (St.status === 'playing' || St.status === 'paused') {
        e.preventDefault();
        if (!e.repeat) tetrisSetPaused(St.status === 'playing');
      }
      return;
    }
    if (St.status !== 'playing') return;
    var a = '', rep = false;
    if (code === 'ArrowLeft' || code === 'KeyA') { a = 'left'; rep = true; }
    else if (code === 'ArrowRight' || code === 'KeyD') { a = 'right'; rep = true; }
    else if (code === 'ArrowDown' || code === 'KeyS') { a = 'down'; rep = true; }
    else if (code === 'ArrowUp' || code === 'KeyW' || code === 'KeyX') a = 'rotate';
    else if (code === 'KeyZ') a = 'rotateccw';
    else if (code === 'Space') a = 'drop';
    if (!a) return;
    e.preventDefault();
    if (e.repeat && !rep) return;
    tetrisAct(a);
  };
  // пробіл на сфокусованій кнопці не має ще й «клікати» її під час гри
  tetrisKeyUp = function (e) {
    var St = tetrisState;
    if (St && St.status === 'playing' && e.code === 'Space' && e.target.tagName === 'BUTTON') e.preventDefault();
  };
  tetrisVis = function () {
    if (document.hidden) tetrisSetPaused(true);
  };
  document.addEventListener('keydown', tetrisKeyDown);
  document.addEventListener('keyup', tetrisKeyUp);
  document.addEventListener('visibilitychange', tetrisVis);

  S.last = performance.now();
  S.raf = requestAnimationFrame(tetrisFrame);
}




/* ================= ГРА «ХТО ЦЕ СКАЗАВ?» (сторінка #quiz, неділя) ================= */
function initQuiz() {
  var data = document.getElementById('quizData');
  var board = document.getElementById('qBoard');
  if (!data || !board) return;
  var Q;
  try { Q = dec(data.textContent.trim()); } catch (e) { return; }
  if (!Q || !Q.length) return;

  var day = data.dataset.day || 'default', gname = data.dataset.name || 'Вісник';
  var KEY = 'gazeta-quiz-' + day;
  var st = store(KEY) || { answers: [], score: 0, over: false };
  if (!st.answers || !Array.isArray(st.answers)) st = { answers: [], score: 0, over: false };
  var el = mkEl;
  var startEl = document.getElementById('qStart'), endEl = document.getElementById('qEnd'), resEl = document.getElementById('qResult');
  var dotsEl = document.getElementById('qDots'), bodyEl = document.getElementById('qBody');
  var i = 0, score = st.score || 0;

  function show(which, instant) {
    startEl.hidden = which !== 'start';
    endEl.hidden = which !== 'end';
    endEl.classList.toggle('is-instant', !!instant);
    board.style.visibility = which ? 'hidden' : '';
    if (which) board.setAttribute('inert', ''); else board.removeAttribute('inert');
  }

  function dots() {
    dotsEl.innerHTML = '';
    Q.forEach(function (q, k) {
      var cls = 'quiz__dot';
      if (st.answers[k]) cls += st.answers[k].correct ? ' is-correct' : ' is-wrong';
      else if (k === i && !st.over) cls += ' is-active';
      dotsEl.appendChild(el('span', cls));
    });
  }

  function ask() {
    dots();
    bodyEl.innerHTML = '';
    var q = Q[Math.min(i, Q.length - 1)];
    var done = st.answers[i];
    bodyEl.appendChild(el('p', 'quiz__bubble', q.text));
    bodyEl.appendChild(el('p', 'quiz__time', (q.date ? q.date + ' · ' : '') + (q.time ? 'написано о ' + q.time : 'з переписки тижня')));

    var opts = el('div', 'quiz__options'), btns = [];
    var bar = el('div', 'quiz__actions');
    var nx = el('button', 'btn btn--primary', i + 1 < Q.length ? 'Наступне питання' : 'Завершити');
    if (i + 1 < Q.length) { var ar = document.createElement('i'); ar.className = 'arrow arrow--right'; ar.setAttribute('aria-hidden', 'true'); nx.appendChild(ar); }
    nx.type = 'button'; nx.disabled = !done;
    nx.onclick = function () {
      if (nx.disabled) return;
      i++;
      if (i < Q.length) { ask(); return; }
      st.over = true; st.score = score; store(KEY, st);
      buildResult(); show('end');
    };
    q.options.forEach(function (o, k) {
      var b = el('button', 'quiz__option', o); b.type = 'button';
      if (done) {
        b.disabled = true;
        if (k === q.answer) b.classList.add('is-right');
        if (k === done.picked && !done.correct) b.classList.add('is-wrong');
      } else {
        b.onclick = function () {
          btns.forEach(function (x) { x.disabled = true; });
          btns[q.answer].classList.add('is-right');
          var ok = k === q.answer;
          if (ok) score++; else b.classList.add('is-wrong');
          st.answers[i] = { picked: k, correct: ok }; st.score = score; store(KEY, st);
          dots();
          nx.disabled = false; nx.focus({ preventScroll: true });
        };
      }
      btns.push(b); opts.appendChild(b);
    });
    bodyEl.appendChild(opts);
    bar.appendChild(nx);
    bodyEl.appendChild(bar);
  }

  function buildResult() {
    resEl.textContent = '';
    var r = score / Q.length;
    resEl.appendChild(el('div', 'quiz__score', score + ' / ' + Q.length));
    resEl.appendChild(el('h2', 'u-display game-start__title', r === 1 ? '🎉 Бездоганно!' : r >= .6 ? 'Непогано!' : r >= .3 ? 'Щось знайоме є' : 'Тільки заради мемів 🙂'));
    resEl.appendChild(el('p', 'game-start__text', r === 1 ? 'Ти знаєш цей чат краще за його учасників.' :
      r >= .6 ? 'Видно, що читаєш чат, а не тільки стікери.' :
        r >= .3 ? 'Щось знайоме є, але варто гортати уважніше.' : 'Схоже, ти в чаті тільки заради мемів і картинок.'));
    var pat = el('div', 'quiz__pattern'); pat.setAttribute('aria-hidden', 'true');
    st.answers.forEach(function (a) { pat.appendChild(el('span', a && a.correct ? '' : 'is-wrong')); });
    resEl.appendChild(pat);
    var copy = el('button', 'btn btn--primary', 'Скопіювати результат'); copy.type = 'button';
    copy.onclick = function () {
      var emojis = st.answers.map(function (a) { return a && a.correct ? '🟩' : '🟥'; }).join('');
      copyText(gname + ' · Вікторина цитат (' + day + ')\nРахунок: ' + score + '/' + Q.length + ' 💬\n' + emojis, copy);
    };
    resEl.appendChild(copy);
    var again = el('button', 'btn', 'Пройти ще раз'); again.type = 'button';
    again.onclick = function () {
      st = { answers: [], score: 0, over: false }; store(KEY, st);
      i = 0; score = 0; ask(); show(null);
    };
    resEl.appendChild(again);
  }

  document.getElementById('qStartBtn').onclick = function () { show(null); };

  if (st.over || st.answers.length >= Q.length) {
    i = Q.length; score = st.score || 0;
    dots(); buildResult(); show('end', true);
  } else {
    i = st.answers.length;
    ask();
    show(st.answers.length ? null : 'start', true);
  }
}


/* ================= КРОСВОРД (сторінка #crossword) ================= */
function initCrossword() {
  var data = document.getElementById('cwData');
  var grid = document.getElementById('cwg');
  if (!data || !grid) return;
  var D;
  try { D = dec(data.textContent.trim()); } catch (e) { return; }
  var KEY = 'gazeta-cw-' + (data.dataset.day || 'default');
  var cells = {}, starts = {}, cur = 0, list = [];
  var E = D.entries;
  var $ = function (id) { return document.getElementById(id); };

  var card = grid.closest('.game-board');
  var avail = (card ? card.clientWidth : window.innerWidth) - 2 * 30;
  if (window.innerWidth > 760) avail -= 28 + 260;
  var size = Math.max(24, Math.min(38, Math.floor(avail / D.w) - 2));
  grid.style.setProperty('--cs', size + 'px');
  grid.style.gridTemplateColumns = 'repeat(' + D.w + ', var(--cs))';

  E.forEach(function (e, i) {
    e.cells = [];
    for (var k = 0; k < e.ans.length; k++) {
      var r = e.r + (e.d === 'd' ? k : 0), c = e.c + (e.d === 'a' ? k : 0), id = r + '_' + c;
      var cell = cells[id] || (cells[id] = { id: id, r: r, c: c, ch: e.ans[k], e: {} });
      cell.e[e.d] = i;
      e.cells.push(cell);
    }
    starts[e.r + '_' + e.c] = e.n;
  });

  var saved = store(KEY) || {};
  for (var r = 0; r < D.h; r++) for (var c = 0; c < D.w; c++) {
    var id = r + '_' + c, div = document.createElement('div'), cell = cells[id];
    if (cell) {
      div.className = 'crossword__cell';
      if (starts[id]) { var n = document.createElement('span'); n.className = 'crossword__cell-num'; n.textContent = starts[id]; div.appendChild(n); }
      var inp = document.createElement('input');
      inp.maxLength = 2; inp.autocomplete = 'off'; inp.spellcheck = false;
      inp.setAttribute('autocapitalize', 'characters');
      inp.setAttribute('aria-label', 'Клітинка ' + (r + 1) + ', ' + (c + 1));
      inp.value = saved[id] || '';
      div.appendChild(inp);
      cell.el = div; cell.inp = inp;
      (function (cell) {
        cell.inp.addEventListener('focus', function () { select(cell, null); });
        cell.inp.addEventListener('mousedown', function () {
          if (document.activeElement === cell.inp && cell.e.a !== undefined && cell.e.d !== undefined)
            setTimeout(function () { select(cell, E[cur].d === 'a' ? 'd' : 'a'); }, 0);
        });
        cell.inp.addEventListener('input', function () {
          var v = cell.inp.value.toUpperCase().replace(/[^А-ЯҐЄІЇ]/g, '');
          cell.inp.value = v.slice(-1);
          cell.el.classList.remove('is-bad', 'is-ok');
          save();
          if (cell.inp.value) move(cell, 1);
        });
        cell.inp.addEventListener('keydown', function (ev) { keys(ev, cell); });
      })(cell);
    }
    grid.appendChild(div);
  }

  ['a', 'd'].forEach(function (d) {
    var ol = $(d === 'a' ? 'cwa' : 'cwd');
    E.forEach(function (e, i) {
      if (e.d !== d) return;
      var li = document.createElement('li');
      li.innerHTML = '<b></b><span></span>';
      li.firstChild.textContent = e.n;
      li.lastChild.textContent = e.clue + ' (' + e.ans.length + ')';
      li.onclick = function () { cur = i; e.cells[0].inp.focus(); select(e.cells[0], d); };
      ol.appendChild(li);
      list[i] = li;
    });
  });

  function select(cell, dir) {
    var want = dir || (E[cur] && cell.e[E[cur].d] !== undefined ? E[cur].d : (cell.e.a !== undefined ? 'a' : 'd'));
    if (cell.e[want] === undefined) want = want === 'a' ? 'd' : 'a';
    cur = cell.e[want];
    Object.keys(cells).forEach(function (k) { cells[k].el.classList.remove('is-highlight', 'is-cursor'); });
    E[cur].cells.forEach(function (x) { x.el.classList.add('is-highlight'); });
    cell.el.classList.add('is-cursor');
    list.forEach(function (li, i) { if (li) li.classList.toggle('is-active', i === cur); });
    var cwc = $('cwcur'), cwa = document.createElement('i');
    cwc.textContent = E[cur].n;
    cwa.className = 'arrow ' + (E[cur].d === 'a' ? 'arrow--right' : 'arrow--down');
    cwa.setAttribute('aria-hidden', 'true');
    cwc.appendChild(cwa);
    cwc.appendChild(document.createTextNode(' ' + E[cur].clue));
  }
  function move(cell, step) {
    var e = E[cur], i = e.cells.indexOf(cell) + step;
    if (i >= 0 && i < e.cells.length) e.cells[i].inp.focus();
  }
  function keys(ev, cell) {
    var l = letterOf(ev);
    if (l && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {  /* працює з будь-якою розкладкою клавіатури */
      ev.preventDefault();
      cell.inp.value = l; cell.el.classList.remove('is-bad', 'is-ok', 'is-revealed');
      save(); move(cell, 1);
      return;
    }
    var map = { ArrowRight: [0, 1, 'a'], ArrowLeft: [0, -1, 'a'], ArrowDown: [1, 0, 'd'], ArrowUp: [-1, 0, 'd'] };
    if (ev.key === 'Backspace' && !cell.inp.value) {
      ev.preventDefault();
      var e = E[cur], i = e.cells.indexOf(cell);
      if (i > 0) { var p = e.cells[i - 1]; p.inp.value = ''; p.el.classList.remove('is-bad', 'is-ok'); p.inp.focus(); save(); }
    } else if (map[ev.key]) {
      ev.preventDefault();
      var m = map[ev.key], nx = cells[(cell.r + m[0]) + '_' + (cell.c + m[1])];
      if (cell.e[m[2]] !== undefined && E[cur].d !== m[2]) { select(cell, m[2]); return; }
      if (nx) { nx.inp.focus(); select(nx, nx.e[m[2]] !== undefined ? m[2] : null); }
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      var next = E[(cur + 1) % E.length]; next.cells[0].inp.focus(); select(next.cells[0], next.d);
    }
  }
  function all() { return Object.keys(cells).map(function (k) { return cells[k]; }); }
  function save() {
    var s = {}, filled = 0, cs = all();
    cs.forEach(function (x) { if (x.inp.value) { s[x.id] = x.inp.value; filled++; } });
    store(KEY, s);
    $('cwp').textContent = filled + ' / ' + cs.length + ' клітинок';
    E.forEach(function (e, i) { list[i].classList.toggle('is-done', e.cells.every(function (x) { return x.inp.value === x.ch; })); });
    if (cs.every(function (x) { return x.inp.value === x.ch; }) && !cs.some(function (x) { return x.el.classList.contains('is-revealed'); }))
      $('cwm').textContent = '🎉 Кросворд розгадано! Редакція аплодує стоячи.';
  }
  $('cwc').onclick = function () {
    var bad = 0, empty = 0;
    all().forEach(function (x) {
      x.el.classList.remove('is-bad', 'is-ok');
      if (!x.inp.value) empty++;
      else if (x.inp.value !== x.ch) { x.el.classList.add('is-bad'); bad++; }
      else x.el.classList.add('is-ok');
    });
    $('cwm').textContent = bad ? 'Помилок: ' + bad + (empty ? ', порожніх клітинок: ' + empty : '')
      : (empty ? 'Поки без помилок, залишилось ' + empty + ' клітинок' : '🎉 Усе правильно!');
  };
  function reveal(cs) { cs.forEach(function (x) { if (x.inp.value !== x.ch) { x.inp.value = x.ch; x.el.classList.add('is-revealed'); } x.el.classList.remove('is-bad'); }); save(); }
  $('cww').onclick = function () { reveal(E[cur].cells); };
  $('cwr').onclick = function () { if (confirm('Показати всі відповіді?')) { reveal(all()); $('cwm').textContent = 'Відповіді показано — наступного разу без підглядань 🙂'; } };
  $('cwx').onclick = function () {
    all().forEach(function (x) { x.inp.value = ''; x.el.classList.remove('is-bad', 'is-ok', 'is-revealed'); });
    $('cwm').textContent = ''; save();
  };
  save();
}


/* ================= НАВІГАЦІЯ ПО ВИПУСКУ =================
   Один автономний HTML-файл: «сторінки» (головна / новина / гра) перемикаються в пам'яті.
   Адреса в браузері НЕ змінюється, але історія працює: кнопка «Назад» і свайп повертають
   на попередній вигляд (через history.state), а положення прокрутки головної запам'ятовується.
   Розмітка: <a href="#slug">…</a>  +  <template id="tpl-slug">…</template>. */
var currentView = 'main';
var mainScrollY = 0;
var NAV_KEY = 'gazeta-nav'; /* sessionStorage: позиція головної, щоб після перезавантаження «До випуску» вертало туди, де читали */
var lastTrigger = null;
var baseTitle = document.title;
var GAME_INIT = {
  wordle: function () { if (window.initWordle) initWordle(); },
  tetris: function () { if (window.initTetris) initTetris(); },
  quiz: function () { initQuiz(); },
  crossword: function () { initCrossword(); }
};

function scrollNow(y) {
  window.scrollTo({ top: y, left: 0, behavior: 'instant' });
}

/* ================= ПРОЧИТАНІ НОВИНИ =================
   Новина вважається прочитаною, щойно її відкрито (як відвідане посилання). Сховище — ОДИН ключ
   "gazeta-read" для всіх випусків, значення — масив рядків "випуск/slug"; нова прочитана новина дописується
   в кінець. Щоб ключ не ріс нескінченно, зберігаємо лише останні READ_MAX записів (старіші випуски забуваються).
   Якщо сховище недоступне — працює до перезавантаження сторінки.
   Позначки ставляться скрізь, де є посилання на новину: плитки «Головне», «Читайте також» на сторінках
   новин і ігор. Прогрес рахується окремо для кожного блоку (новини дня / дні тижня). */
var READ_KEY = 'gazeta-read', READ_MAX = 600;
var readPrefix = ((document.body && document.body.dataset.issue) || 'issue') + '/';
var readSet = {};
(function () {
  var a = store(READ_KEY);
  if (Array.isArray(a)) a.forEach(function (e) {
    if (typeof e === 'string' && e.indexOf(readPrefix) === 0) readSet[e.slice(readPrefix.length)] = 1;
  });
})();

/* «Близнюки»: новина тижня, що збігається з новиною дня, має власну сторінку (data-twin на шаблоні) —
   прочитаність спільна для обох сторінок і обох плиток */
var TWINS = null;
function twinsOf(slug) {
  if (!TWINS) {
    TWINS = {};
    document.querySelectorAll('template[data-twin]').forEach(function (t) {
      var x = t.id.slice(4), y = t.getAttribute('data-twin');
      (TWINS[x] = TWINS[x] || []).push(y);
      (TWINS[y] = TWINS[y] || []).push(x);
    });
    Object.keys(readSet).forEach(function (k) { (TWINS[k] || []).forEach(function (t) { readSet[t] = 1; }); });
  }
  return TWINS[slug] || [];
}
function markRead(slug) {
  if (!slug) return;
  var add = [slug].concat(twinsOf(slug)).filter(function (s) { return !readSet[s]; });
  if (!add.length) return;
  var a = store(READ_KEY);
  if (!Array.isArray(a)) a = [];          // читаємо заново: у іншій вкладці могли дописати свої записи
  add.forEach(function (s) {
    readSet[s] = 1;
    var rec = readPrefix + s;
    if (a.indexOf(rec) < 0) a.push(rec);
  });
  if (a.length > READ_MAX) a = a.slice(a.length - READ_MAX);
  store(READ_KEY, a);
}
function slugOf(a) { return (a.getAttribute('href') || '').slice(1); }

/* список «Читайте також» без смуги прокрутки: згасання зверху/знизу показує, куди ще можна гортати */
function bindListFade(el) {
  if (!el) return;
  function upd() {
    var max = el.scrollHeight - el.clientHeight;
    el.style.setProperty('--fade-t', Math.min(el.scrollTop, 28) + 'px');
    el.style.setProperty('--fade-b', Math.max(0, Math.min(max - el.scrollTop, 28)) + 'px');
  }
  el.addEventListener('scroll', upd, { passive: true });
  upd();
}

function applyReadState(root) {
  if (!root) return;
  twinsOf('');

  /* плитки «Головне» */
  root.querySelectorAll('a.news-tile').forEach(function (a) {
    var on = !!readSet[slugOf(a)];
    if (!a.dataset.t) a.dataset.t = a.getAttribute('aria-label') || '';
    a.classList.toggle('is-read', on);
    a.setAttribute('aria-label', on ? a.dataset.t + ' — прочитано' : a.dataset.t);
  });

  /* блоки «Читайте також»: позначки, прогрес, «Читати далі» */
  var navs = Array.prototype.slice.call(root.querySelectorAll('[data-news-nav]'));
  if (root.matches && root.matches('[data-news-nav]')) navs.unshift(root);
  navs.forEach(function (nav) {
    var items = nav.querySelectorAll('.also-link'), total = items.length, done = 0, firstUnread = null;
    items.forEach(function (a) {
      var r = !!readSet[slugOf(a)];
      a.classList.toggle('is-read', r);
      if (r) done++; else if (!firstUnread) firstUnread = a;
    });
    var txt = nav.querySelector('[data-np-text]'), bar = nav.querySelector('[data-np-bar]');
    if (txt) {
      txt.textContent = done >= total ? 'Усе прочитано' : 'Прочитано ' + done + ' з ' + total;
      if (done >= total) { var ck = document.createElement('i'); ck.className = 'arrow arrow--check'; ck.setAttribute('aria-hidden', 'true'); txt.appendChild(ck); }
    }
    if (bar) bar.style.width = (total ? Math.round(done / total * 100) : 0) + '%';
    var cont = nav.querySelector('[data-continue]');
    if (cont) {
      if (firstUnread) {
        cont.hidden = false;
        cont.setAttribute('href', '#' + slugOf(firstUnread));
        var lb = cont.querySelector('[data-continue-label]');
        if (lb) lb.textContent = done ? 'Читати далі' : 'Почати читати';
      } else cont.hidden = true;
    }
  });

  /* остання новина: якщо лишились непрочитані — «Далі» веде до першої з них, інакше — до випуску */
  root.querySelectorAll('.article-next[data-last]').forEach(function (b) {
    var view = b.closest('.article-view');
    var un = view && view.querySelectorAll('[data-news-nav] .ai:not(.is-read)');
    var a = b.querySelector('.article-next__card');
    var k = b.querySelector('[data-an-kicker]'), t = b.querySelector('[data-an-title]'), l = b.querySelector('[data-an-label]');
    if (un && un.length) {
      a.setAttribute('href', '#' + slugOf(un[0]));
      k.textContent = 'Це остання новина · лишилось непрочитаних: ' + un.length;
      var tt = un[0].querySelector('.also-link__title');
      t.textContent = tt ? tt.textContent : '';
      l.textContent = 'До непрочитаної';
    } else {
      a.setAttribute('href', '#main');
      k.textContent = 'Усі новини випуску прочитано';
      t.textContent = 'Повернутися до випуску';
      l.textContent = 'До випуску';
    }
  });
}

/* «Читайте також» на сторінках ігор додається після запуску гри, щоб мініатюри не гальмували старт */
function deferGameSide(frag) {
  var aside = frag.querySelector('.game-page__side');
  var tpl = document.getElementById('also-card-tpl');
  if (!aside || !tpl || !tpl.content.firstElementChild) return null;
  return function () {
    requestAnimationFrame(function () {
      setTimeout(function () {
        if (!aside.isConnected) return;
        var card = tpl.content.firstElementChild.cloneNode(true);
        hydrate(card); applyReadState(card); aside.appendChild(card);
      }, 0);
    });
  };
}

/* Позначка виду на <html>: CSS стискає шапку на внутрішніх сторінках; логотип лишається h1 тільки на головній
   (на сторінці новини/гри свій h1 — другого заголовка верхнього рівня бути не повинно) */
function chipsFocus() {
  var c = document.querySelector('.masthead__chips');
  if (!c || !c.offsetParent) return;
  var scrolls = c.scrollWidth > c.clientWidth + 1;
  if (scrolls) { c.tabIndex = 0; c.setAttribute('role', 'group'); c.setAttribute('aria-label', 'Про випуск'); }
  else { c.removeAttribute('tabindex'); c.removeAttribute('role'); c.removeAttribute('aria-label'); }
}
window.addEventListener('resize', function () { requestAnimationFrame(chipsFocus); });

function markView(id) {
  document.documentElement.setAttribute('data-view', id === 'main' ? 'main' : 'inner');
  if (id === 'main') requestAnimationFrame(chipsFocus);
  var lg = document.querySelector('.masthead__text h1');
  if (lg) { if (id === 'main') lg.removeAttribute('role'); else lg.setAttribute('role', 'presentation'); }
}

function showView(id) {
  var mainView = document.getElementById('view-main');
  var host = document.getElementById('articleHost');
  if (!mainView || !host) return false;

  if (id === 'main') {
    host.innerHTML = '';
    host.style.display = 'none';
    mainView.style.display = 'block';
    document.title = baseTitle;
    applyReadState(mainView);
    scrollNow(mainScrollY);
    setMainVideos(true);
    if (lastTrigger && mainView.contains(lastTrigger)) lastTrigger.focus({ preventScroll: true });
    currentView = 'main';
    markView('main');
    return true;
  }

  var tpl = document.getElementById('tpl-' + id);
  if (!tpl) return false;

  if (currentView === 'main') {
    mainScrollY = window.scrollY;
    try { sessionStorage.setItem(NAV_KEY, JSON.stringify({ i: readPrefix, y: Math.round(mainScrollY) })); } catch (e) { }
  }
  if (tpl.hasAttribute('data-news')) markRead(id);
  mainView.style.display = 'none';
  setMainVideos(false);
  host.innerHTML = '';
  var frag = tpl.content.cloneNode(true);
  var isGame = !!GAME_INIT[id];
  var lateSide = isGame ? deferGameSide(frag) : null;
  hydrate(frag);
  host.appendChild(frag);
  host.style.display = 'block';
  applyReadState(host);
  /* у довгому списку бічна колонка прокручується до відкритої новини */
  var side = host.querySelector('.article-side .also-list'), curEl = side && side.querySelector('.is-current');
  if (side && curEl && side.scrollHeight > side.clientHeight) {
    side.scrollTop = Math.max(0, curEl.offsetTop - side.offsetTop - (side.clientHeight - curEl.offsetHeight) / 2);
  }
  bindListFade(side);
  scrollNow(0);

  host.setAttribute('tabindex', '-1');
  host.focus({ preventScroll: true });
  var h1 = host.querySelector('h1');
  document.title = (h1 ? h1.textContent.trim() + ' — ' : '') + baseTitle;

  currentView = id;
  markView(id);
  if (GAME_INIT[id]) GAME_INIT[id]();
  if (lateSide) lateSide();
  return true;
}

function openView(id, trigger) {
  if (id === currentView) {
    if (id === 'main') window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  var mainView = document.getElementById('view-main');
  if (trigger && mainView && mainView.contains(trigger)) lastTrigger = trigger;
  if (!showView(id)) return;
  try { history.pushState({ view: id }, ''); } catch (err) { }
}

/* Клік по <a href="#slug">: перехоплюємо, щоб адреса не змінювалась.
   Ctrl/⌘/Shift/середня кнопка лишаються браузеру (відкриття у новій вкладці працює). */
document.addEventListener('click', function (e) {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  var a = e.target.closest('a[href^="#"]');
  if (!a) return;
  var id = a.getAttribute('href').slice(1);
  if (id !== 'main' && !document.getElementById('tpl-' + id)) return;
  e.preventDefault();
  openView(id, a);
});

/* «Назад» (кнопка браузера, жест, Alt+←) при відкритому модальному вікні лише закриває його: showAppModal додає запис
   в історію {modal:true}, а закриття вікна будь-яким способом знімає його через history.back().
   skipPop — скільки найближчих popstate викликані нами самими й не потребують перемикання сторінки. */
var modalHist = false, skipPop = 0;
function dropModalEntry() {
  if (!modalHist) return;
  modalHist = false;
  skipPop++;
  try { history.back(); } catch (e) { skipPop--; return; }
  setTimeout(function () { skipPop = 0; }, 600);
}

window.addEventListener('popstate', function (e) {
  if (skipPop > 0) { skipPop--; return; }
  var st = e.state || {};
  if (appModal && appModal.open) { modalHist = false; closeAppModal(); return; }
  if (st.modal) return; /* «Вперед» на запис закритого вікна: лишаємось на тій самій сторінці */
  var view = st.view || 'main';
  if (view === currentView) return;
  showView(view);
});

try { history.scrollRestoration = 'manual'; } catch (err) { }


// ================= UNIFIED MODAL SYSTEM (APP-MODAL) =================
var appModal = null;
var modalContentView = null;
var modalMediaView = null;
var modalKicker = null;
var modalTitle = null;
var modalBody = null;
var modalMediaContainer = null;
var modalCaption = null;
var modalCounter = null;

var mediaList = [];
var currentMediaIndex = 0;
var activeMediaList = [];

function initModal() {
  appModal = document.getElementById('appModal');
  modalContentView = document.getElementById('modalContentView');
  modalMediaView = document.getElementById('modalMediaView');
  modalKicker = document.getElementById('modalKicker');
  modalTitle = document.getElementById('modalTitle');
  modalBody = document.getElementById('modalBody');
  modalMediaContainer = document.getElementById('modalMediaContainer');
  modalCaption = document.getElementById('modalCaption');
  modalCounter = document.getElementById('modalCounter');

  if (!appModal) return;

  appModal.addEventListener('click', function (e) {
    var tg = e.target;
    // Клік по затемненому фону закриває вікно
    if (tg === appModal) { closeAppModal(); return; }
    // Перегляд медіа: клік у порожнє місце (поза файлом, підписом і кнопками) теж закриває
    if (appModal.classList.contains('is-media') &&
      (tg === modalMediaView || tg === modalMediaContainer ||
        (tg.classList && (tg.classList.contains('modal__stage') || tg.classList.contains('modal__wrap'))))) {
      closeAppModal();
    }
  });
  appModal.addEventListener('close', function () {
    document.documentElement.classList.remove('is-modal-open');
    dropModalEntry();
  });

  // кожна галерея (день / тиждень) гортається окремо
  mediaList = [];
  document.querySelectorAll('.gallery__grid').forEach(function (gal) {
    var list = [];
    gal.querySelectorAll('.gallery__item').forEach(function (btn, idx) {
      var img = btn.querySelector('img');
      var vid = btn.querySelector('video');
      var caption = btn.getAttribute('data-caption') || (btn.querySelector('.gallery__caption') ? btn.querySelector('.gallery__caption').textContent.trim() : '');
      btn.setAttribute('data-gal-index', idx);
      if (vid) list.push({ type: 'video', src: vid.getAttribute('src'), caption: caption });
      else if (img) list.push({ type: 'image', src: img.getAttribute('src'), caption: caption });
      else list.push({ type: 'image', src: '', caption: caption });
    });
    gal._list = list;
    if (!mediaList.length) mediaList = list;
  });

  document.addEventListener('click', function (e) {
    var box = e.target.closest('.article__media');
    var target = box || e.target.closest('[data-lightbox]');
    if (target) {
      if (target.closest('.news-tile--lead') || target.closest('.gallery__grid')) return;

      e.preventDefault();
      e.stopPropagation();

      var container = target.closest('.article__media-grid') || target.closest('.article__body') || target.closest('.article-view');
      var boxes = container ? Array.prototype.slice.call(container.querySelectorAll('.article__media')) : [];

      if (boxes.length > 0) {
        var articleItems = [];
        var clickedIdx = 0;
        var defaultCaption = (container && container.querySelector('.article__title')) ? container.querySelector('.article__title').textContent.trim() : '';

        boxes.forEach(function (b) {
          var fit = b.querySelector('.article__media-fit') || b.querySelector('video, img');
          if (!fit) return;
          var isVid = fit.tagName.toLowerCase() === 'video';
          var src = fit.getAttribute('src');
          var cap = b.getAttribute('data-caption') || fit.getAttribute('data-caption') || fit.getAttribute('alt') || defaultCaption;
          articleItems.push({ type: isVid ? 'video' : 'image', src: src, caption: cap });
          if (b === box || b.contains(e.target)) {
            clickedIdx = articleItems.length - 1;
          }
        });

        openMediaModal(clickedIdx, articleItems);
      } else {
        var mediaElem = /^(IMG|VIDEO)$/.test(target.tagName) ? target : target.querySelector('img, video');
        if (!mediaElem) return;
        var src = mediaElem.getAttribute('src');
        var cap = target.getAttribute('data-caption') || target.getAttribute('alt') || mediaElem.getAttribute('alt') || '';
        var isVid = mediaElem.tagName.toLowerCase() === 'video';
        openMediaModal(0, [{ type: isVid ? 'video' : 'image', src: src, caption: cap }]);
      }
    }
  });

  document.querySelectorAll('.gallery__grid .gallery__item').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var gal = btn.closest('.gallery__grid');
      openMediaModal(parseInt(btn.getAttribute('data-gal-index'), 10) || 0, (gal && gal._list) || mediaList);
    });
  });

  var galleryVideos = document.querySelectorAll('.gallery__grid video');
  galleryVideos.forEach(function (v) {
    v.pause();
    var wrap = v.closest('.gallery__item') || v.parentElement;
    if (!wrap) return;
    wrap.addEventListener('mouseenter', function () { v.play().catch(function () { }); });
    wrap.addEventListener('mouseleave', function () { v.pause(); v.currentTime = 0; });
  });

  var coverVideos = document.querySelectorAll('.news-tile .news-tile__cover video');
  coverVideos.forEach(function (v) {
    v.pause();
    var tile = v.closest('.news-tile');
    if (!tile) return;
    tile.addEventListener('mouseenter', function () { v.play().catch(function () { }); });
    tile.addEventListener('mouseleave', function () { v.pause(); v.currentTime = 0; });
  });
}

// Єдина точка відкриття: блокує прокрутку сторінки, поки вікно відкрите.
// Знімається в обробнику події "close" (Esc, кнопка, клік по фону).
function showAppModal() {
  if (!appModal || appModal.open) return;
  document.documentElement.classList.add('is-modal-open');
  appModal.showModal();
  try { history.pushState({ view: currentView, modal: true }, ''); modalHist = true; } catch (e) { }
}

function openContentModal(kicker, title, contentHtml, opts) {
  if (!appModal) return;
  appModal.classList.remove('is-media');
  appModal.classList.toggle('is-wide', !!(opts && opts.wide));
  modalBody.scrollTop = 0;
  modalContentView.style.display = 'flex';
  modalMediaView.style.display = 'none';

  modalKicker.textContent = kicker;
  modalTitle.textContent = title;
  modalBody.innerHTML = contentHtml;

  showAppModal();
}

function openMediaModal(index, list) {
  if (list) activeMediaList = list;
  if (!activeMediaList || !activeMediaList.length) activeMediaList = mediaList;
  if (!appModal || !activeMediaList || !activeMediaList.length) return;

  appModal.classList.add('is-media');
  modalContentView.style.display = 'none';
  modalMediaView.style.display = 'flex';

  currentMediaIndex = (index + activeMediaList.length) % activeMediaList.length;
  renderMediaItem(activeMediaList[currentMediaIndex], currentMediaIndex + 1, activeMediaList.length);

  var showNav = activeMediaList.length > 1;
  var prevBtn = document.getElementById('modalPrevBtn');
  var nextBtn = document.getElementById('modalNextBtn');
  if (prevBtn) prevBtn.style.display = showNav ? 'grid' : 'none';
  if (nextBtn) nextBtn.style.display = showNav ? 'grid' : 'none';

  showAppModal();
}

function openMediaModalStandalone(item) {
  openMediaModal(0, [item]);
}

var blobCache = {};
function toBlobUrl(dataUri) {
  if (!dataUri || dataUri.indexOf("data:") !== 0) return dataUri;
  dataUri = dataUri.split("#")[0];
  if (blobCache[dataUri]) return blobCache[dataUri];
  try {
    var parts = dataUri.split(",");
    var meta = parts[0], b64 = parts[1];
    var mime = meta.split(":")[1].split(";")[0];
    var bin = atob(b64), len = bin.length, u8 = new Uint8Array(len);
    for (var j = 0; j < len; j++) u8[j] = bin.charCodeAt(j);
    var url = URL.createObjectURL(new Blob([u8], { type: mime }));
    blobCache[dataUri] = url;
    return url;
  } catch (e) { return dataUri; }
}

function renderMediaItem(item, curr, total) {
  modalMediaContainer.innerHTML = '';
  var wrap = document.createElement('div');
  wrap.className = 'modal__wrap';

  var resolvedSrc = toBlobUrl(item.src);

  if (item.type === 'video') {
    var vid = document.createElement('video');
    vid.src = resolvedSrc;
    vid.autoplay = true;
    vid.loop = true;
    vid.controls = true;
    vid.playsInline = true;
    wrap.appendChild(vid);
  } else {
    var img = document.createElement('img');
    img.src = resolvedSrc;
    img.alt = item.caption || 'Зображення';
    wrap.appendChild(img);
  }

  modalMediaContainer.appendChild(wrap);
  modalCaption.textContent = item.caption || '';
  modalCounter.textContent = total > 1 ? (curr + ' / ' + total) : '';
  preloadNeighbours();
}

function prevMedia() {
  var list = activeMediaList && activeMediaList.length ? activeMediaList : mediaList;
  if (list && list.length > 1) {
    openMediaModal(currentMediaIndex - 1);
  }
}

function nextMedia() {
  var list = activeMediaList && activeMediaList.length ? activeMediaList : mediaList;
  if (list && list.length > 1) {
    openMediaModal(currentMediaIndex + 1);
  }
}

function closeAppModal() {
  if (appModal && appModal.open) {
    var vid = modalMediaContainer.querySelector('video');
    if (vid) vid.pause();
    appModal.close();
  }
}

window.addEventListener('keydown', function (e) {
  if (!appModal || !appModal.open) return;
  if (e.key === 'Escape') {
    closeAppModal();
  } else if (modalMediaView && modalMediaView.style.display !== 'none') {
    if (e.key === 'ArrowLeft') prevMedia();
    else if (e.key === 'ArrowRight') nextMedia();
  }
});

/* свайп у перегляді медіа: вліво — далі, вправо — назад; сусідні кадри готуються наперед */
(function () {
  var x0 = null, y0 = 0;
  var box = document.getElementById('modalMediaView');
  if (!box) return;
  box.addEventListener('touchstart', function (e) {
    if (e.touches.length !== 1 || e.target.closest('video[controls]')) { x0 = null; return; }
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
  }, { passive: true });
  box.addEventListener('touchend', function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    x0 = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) { if (dx < 0) nextMedia(); else prevMedia(); }
  }, { passive: true });
})();
function preloadNeighbours() {
  var l = activeMediaList;
  if (!l || l.length < 2) return;
  [1, -1].forEach(function (d) {
    var it = l[(currentMediaIndex + d + l.length) % l.length];
    if (it && it.type === 'image') (window.requestIdleCallback || setTimeout)(function () { toBlobUrl(it.src); });
  });
}


/* Вибір стовпчика в «Детально» (години/дні): підпис і позначка беруться з data-атрибутів кнопок (data-rt, data-rs, data-pk).
   Наведення лише змінює підпис; скринрідеру він озвучується (aria-live) тільки після кліку або стрілок. */
function wireStatsBars() {
  var bars = [].slice.call(modalBody.querySelectorAll('.stats-detail__bar'));
  var readout = modalBody.querySelector('.stats-detail__readout');
  if (!bars.length || !readout) return;
  var peak = Math.max(0, bars.findIndex(function (b) { return b.classList.contains('is-peak'); }));
  function select(i, announce, focus) {
    bars.forEach(function (b, k) {
      var on = k === i;
      b.classList.toggle('is-selected', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    readout.setAttribute('aria-live', announce ? 'polite' : 'off');
    var b = bars[i], t = document.createElement('strong'), s = document.createElement('span');
    t.className = 'u-display'; t.textContent = b.getAttribute('data-rt');
    s.textContent = b.getAttribute('data-rs');
    if (b.getAttribute('data-pk')) { s.appendChild(document.createTextNode(' · ')); var pk = document.createElement('b'); pk.textContent = b.getAttribute('data-pk'); s.appendChild(pk); }
    readout.textContent = '';
    readout.appendChild(t); readout.appendChild(s);
    if (focus) b.focus();
  }
  bars.forEach(function (b, i) {
    b.addEventListener('click', function () { select(i, true); });
    b.addEventListener('mouseenter', function () { select(i, false); });
    b.addEventListener('keydown', function (e) {
      var to = e.key === 'ArrowLeft' ? Math.max(0, i - 1) : e.key === 'ArrowRight' ? Math.min(bars.length - 1, i + 1)
        : e.key === 'Home' ? 0 : e.key === 'End' ? bars.length - 1 : -1;
      if (to < 0) return;
      e.preventDefault();
      select(to, true, true);
    });
  });
  select(peak, false);
}


// ================= WIDGET LOGIC =================
document.addEventListener('DOMContentLoaded', function () {
  try { hydrate(document.getElementById('view-main')); } catch (e) { }
  try { applyReadState(document.getElementById('view-main')); } catch (e) { }
  initModal();

  // 1: Анекдоти — «Хочу ще» (усі тексти в одній ячейці, щоб висота плитки не стрибала)
  var jokeIndex = 0;
  var tplJokes = document.getElementById('tplJokes');
  var jokes = [];
  if (tplJokes) {
    try {
      var parsed = JSON.parse(tplJokes.textContent);
      if (Array.isArray(parsed)) jokes = parsed;
    } catch (e) { }
  }
  var jokeStackEl = document.getElementById('jokeStack');
  var jokeNodes = [];
  var jokeCounterEl = document.getElementById('jokeCounter');
  var nextJokeBtn = document.getElementById('nextJoke');

  if (jokeStackEl && jokes.length) {
    jokeStackEl.innerHTML = '';
    jokes.forEach(function (text) {
      var p = document.createElement('p');
      p.className = 'joke__text';
      p.textContent = text;
      jokeStackEl.appendChild(p);
      jokeNodes.push(p);
    });
  }

  function renderJokeView() {
    if (!jokes.length || !jokeNodes.length) return;
    jokeNodes.forEach(function (p, k) {
      var on = k === jokeIndex;
      p.classList.toggle('is-active', on);
      p.setAttribute('aria-hidden', on ? 'false' : 'true');
    });
    if (jokeCounterEl) {
      jokeCounterEl.textContent = String(jokeIndex + 1).padStart(2, '0') + ' / ' + String(jokes.length).padStart(2, '0');
    }
  }

  if (nextJokeBtn) {
    nextJokeBtn.addEventListener('click', function () {
      if (!jokes.length) return;
      jokeIndex = (jokeIndex + 1) % jokes.length;
      renderJokeView();
    });
  }

  renderJokeView();

  // 3: «Детально» у цифрах дня й тижня. Вміст вікна вже зверстано в <template id="tpl-stats-day|week"> (числа рахує
  // бекенд, page_data.py); тут лише відкриття вікна та вибір стовпчика.
  function bindStatsDetail(btnId, tplId) {
    var btn = document.getElementById(btnId);
    if (!btn) return;
    var tpl = document.getElementById(tplId);
    if (!tpl) { btn.hidden = true; return; }
    btn.addEventListener('click', function () {
      openContentModal(tpl.getAttribute('data-title') || '', 'Детально', tpl.innerHTML, { wide: true });
      wireStatsBars();
    });
  }
  bindStatsDetail('statsDetail', 'tpl-stats-day');
  bindStatsDetail('weekStatsDetail', 'tpl-stats-week');

});


/* ================= СТАРТ: який вигляд показати =================
   Слухач навмисно останній: усі віджети головної вже ініціалізовані, поки головна ще видима.
   1) посилання з #slug — відкриваємо цю сторінку (адресу одразу очищаємо від #);
   2) перезавантаження — history.state переживає його, тож повертаємось на ту саму сторінку (без # в адресі);
   3) інакше головна. */
document.addEventListener('DOMContentLoaded', function () {
  var id = (location.hash || '').slice(1), st = null, clean = location.pathname + location.search;
  try { st = history.state; } catch (err) { }
  var saved = (st && st.view && !st.modal && st.view !== 'main') ? st.view : '';
  function setState(v) {
    try { history.replaceState({ view: v }, '', clean); } catch (err) { try { history.replaceState({ view: v }, ''); } catch (err2) { } }
  }
  if (id && id !== 'main') { setState('main'); openView(id); return; }
  if (saved && document.getElementById('tpl-' + saved)) {
    var y = null;
    try {
      var n = JSON.parse(sessionStorage.getItem(NAV_KEY));
      if (n && n.i === readPrefix && typeof n.y === 'number') y = n.y;
    } catch (err) { }
    if (showView(saved)) {
      /* showView запам'ятав би позицію «головної» як 0 (її ще не прокручували) — повертаємо збережену */
      if (y !== null) {
        mainScrollY = y;
        try { sessionStorage.setItem(NAV_KEY, JSON.stringify({ i: readPrefix, y: y })); } catch (err) { }
      }
      setState(saved);
      return;
    }
  }
  setState('main');
  chipsFocus();
});
