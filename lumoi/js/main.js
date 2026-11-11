/* LUMOI — ページの動き（ナビ・鏡・印象の切り替え・予約のデモ・動きを止めるボタン）
   外への通信はしない。フォームはどこにも送らない。 */
(function () {
  'use strict';

  var doc = document, root = doc.documentElement;
  var $ = function (s, c) { return (c || doc).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || doc).querySelectorAll(s)); };
  var clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };

  /* ---------- ナビ（1か所直せば3か所に出る） ---------- */
  var NAV = [
    { href: '#concept', label: 'コンセプト', la: 'Philosophy' },
    { href: '#visage', label: 'なりたい印象', la: 'Impressions' },
    { href: '#menu', label: '料金', la: 'Menu' },
    { href: '#first', label: 'はじめての方へ', la: 'First visit' },
    { href: '#stylist', label: 'スタイリスト', la: 'Stylists' },
    { href: '#faq', label: 'よくある質問', la: 'Questions' },
    { href: '#access', label: 'アクセス', la: 'Access' },
    { href: '#reserve', label: 'ご予約', la: 'Reservation' }
  ];
  function buildNav(id, withLatin, skipReserve) {
    var ul = doc.getElementById(id); if (!ul) return;
    NAV.forEach(function (n) {
      if (skipReserve && n.href === '#reserve') return;
      if (id === 'navPc' && n.href === '#faq') return;
      var li = doc.createElement('li'), a = doc.createElement('a');
      a.href = n.href; a.textContent = n.label;
      if (withLatin) { var s = doc.createElement('small'); s.textContent = n.la; a.appendChild(s); }
      li.appendChild(a); ul.appendChild(li);
    });
  }
  buildNav('navPc', false, true); buildNav('navSp', true, false); buildNav('navFt', false, false);

  /* 最初の画面に関係ない準備は、その章が近づいたときにする（最初の表示と操作を待たせない。見ない章の分は動かさない） */
  var nearJobs = [];
  var nearIO = ('IntersectionObserver' in window) ? new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      nearIO.unobserve(e.target);
      nearJobs.filter(function (j) { return j.el === e.target; }).forEach(function (j) { j.fn(); });
    });
  }, { rootMargin: '900px 0px' }) : null;
  function later(sel, fn) {
    var el = doc.querySelector(sel);
    if (!el) return;
    if (!nearIO) { setTimeout(fn, 200); return; }
    nearJobs.push({ el: el, fn: fn }); nearIO.observe(el);
  }

  /* ---------- 印象の設定 ---------- */
  var ORDER = ['douce', 'nette', 'eclat', 'claire', 'legere'];
  var IMP = {
    douce:  { jp: 'やわらかく', fr: 'Douce', menu: 'cut-color', silk: ['#f6ede4', '#ecd8cd', '#e7dccb', '#fffaf4'] },
    nette:  { jp: '凛と', fr: 'Nette', menu: 'course', silk: ['#eeeaf0', '#d9d5e0', '#e3dcd6', '#fbfaff'] },
    eclat:  { jp: '華やかに', fr: 'Éclatante', menu: 'cut-perm-color', silk: ['#f7e9e4', '#ecccc6', '#ead9cd', '#fff6f2'] },
    claire: { jp: '透けるように', fr: 'Claire', menu: 'cut-hl', silk: ['#f1efe6', '#dfdccb', '#e8e2d6', '#fdfcf5'] },
    legere: { jp: '軽やかに', fr: 'Légère', menu: 'cut-color', silk: ['#f7efdf', '#ecd9b4', '#efe2cf', '#fffaf0'] }
  };

  /* ---------- 動きを止める ---------- */
  var still = root.classList.contains('is-still');
  var actors = [];                       /* 見えているあいだだけ動かす物 */
  var motionBtn = $('#motionToggle'), motionLabel = $('#motionLabel');
  function paintMotionBtn() {
    motionBtn.setAttribute('aria-pressed', still ? 'true' : 'false');
    motionLabel.textContent = still ? '動きを再開する' : '動きを止める';
  }
  function syncActors() {
    actors.forEach(function (a) {
      if (a.visible && !still && !doc.hidden) a.obj.start(); else a.obj.stop();
    });
  }
  function setStill(v) {
    still = v;
    root.classList.toggle('is-still', v);
    try { sessionStorage.setItem('lumoi-motion', v ? 'off' : 'on'); } catch (e) {}
    paintMotionBtn();
    if (v) {
      clearTimeout(capTimer);
      if (heroCap) { heroCap.classList.remove('is-out'); heroFr.textContent = IMP[ORDER[heroIdx]].fr; heroJp.textContent = IMP[ORDER[heroIdx]].jp; }
      actors.forEach(function (a) { if (a.obj.finish) a.obj.finish(); });
      $$('[data-reveal], [data-lines], .map').forEach(function (el) { el.classList.add('is-in'); });
      $$('[data-parallax]').forEach(function (el) { el.style.transform = ''; });
      var fl = $('#flow'); if (fl) fl.style.setProperty('--p', 1);
    }
    syncActors();
    if (!v) { onScroll(); scheduleCycle(); }
  }
  motionBtn.addEventListener('click', function () { setStill(!still); });
  paintMotionBtn();
  if (still) { var fl0 = $('#flow'); if (fl0) fl0.style.setProperty('--p', 1); }
  doc.addEventListener('visibilitychange', syncActors);

  var seen = ('IntersectionObserver' in window) ? new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      actors.forEach(function (a) { if (a.el === e.target) { a.visible = e.isIntersecting; if (e.isIntersecting && a.onFirst) { a.onFirst(); a.onFirst = null; } } });
    });
    syncActors();
  }, { rootMargin: '80px' }) : null;
  function addActor(el, obj, onFirst) {
    var a = { el: el, obj: obj, visible: !seen, onFirst: onFirst || null };
    actors.push(a);
    if (seen) seen.observe(el); else if (onFirst) onFirst();
    return a;
  }
  /* 大きさは ResizeObserver から受け取る（自分で測り直さない） */
  var ro = ('ResizeObserver' in window) ? new ResizeObserver(function (es) { es.forEach(function (e) { actors.forEach(function (a) { if (a.el === e.target && a.obj.resize) a.obj.resize(e.contentRect.width, e.contentRect.height); }); }); }) : null;
  if (!ro) window.addEventListener('load', function () { actors.forEach(function (a) { if (a.obj.resize) a.obj.resize(); }); });

  /* ---------- 鏡（最初の画面） ---------- */
  var Figure = window.LumoiFigure, Silk = window.LumoiSilk;
  var heroFig = null, heroSilk = null, heroIdx = 0, cycleTimer = 0, capTimer = 0;
  var heroCap = $('.hero .mirror__cap'), heroFr = $('#heroFr'), heroJp = $('#heroJp'), heroDots = $$('#heroDots li');
  var heroEl = $('#top');

  if (Figure && $('#heroFig')) {
    heroFig = new Figure($('#heroFig'), { style: ORDER[0], grow: !still, seed: 11 });
    addActor($('#heroFig'), heroFig);
    if (ro) ro.observe($('#heroFig'));
  }
  if (Silk && $('#heroSilk')) {
    heroSilk = new Silk($('#heroSilk'), { colors: IMP[ORDER[0]].silk });
    if (heroSilk.ok) { addActor($('#heroSilk'), heroSilk); if (ro) ro.observe($('#heroSilk')); }
    heroEl.addEventListener('pointermove', function (e) {
      if (still) return;
      var r = heroEl.getBoundingClientRect();
      heroSilk.setPointer((e.clientX - r.left) / r.width, 1 - (e.clientY - r.top) / r.height);
    }, { passive: true });
  }
  function heroShow(i) {
    heroIdx = i; var key = ORDER[i], d = IMP[key];
    if (heroFig) heroFig.setStyle(key, still ? 0 : 1900);
    if (heroSilk && heroSilk.ok) heroSilk.setColors(d.silk, still ? 0 : 1900);
    heroDots.forEach(function (li, k) { li.classList.toggle('is-on', k === i); });
    if (still) { heroFr.textContent = d.fr; heroJp.textContent = d.jp; return; }
    heroCap.classList.add('is-out');
    clearTimeout(capTimer);
    capTimer = setTimeout(function () { heroFr.textContent = d.fr; heroJp.textContent = d.jp; heroCap.classList.remove('is-out'); }, 520);
  }
  function scheduleCycle() {
    clearTimeout(cycleTimer);
    if (still) return;
    cycleTimer = setTimeout(function tick() {
      var a = actors.filter(function (x) { return heroFig && x.obj === heroFig; })[0];
      if (!still && !doc.hidden && a && a.visible) heroShow((heroIdx + 1) % ORDER.length);
      cycleTimer = setTimeout(tick, 4800);
    }, 5200);
  }
  scheduleCycle();

  /* ---------- なりたい印象を選ぶ ---------- */
  var visage = $('#visage'), impBtns = $$('#visageList .imp'), props = $$('#visageCard .prop');
  var visFig = null, visSilk = null, visStyle = 'douce';
  later('#visage', function () {
    if (Figure && $('#visageFig')) {
      visFig = new Figure($('#visageFig'), { style: visStyle, grow: !still, seed: 23 });
      addActor($('#visageFig'), visFig);
      if (ro) ro.observe($('#visageFig'));
    }
  });
  later('#visage', function () {
    if (Silk && $('#visageSilk')) {
      visSilk = new Silk($('#visageSilk'), { colors: IMP[visStyle].silk });
      if (visSilk.ok) { addActor($('#visageSilk'), visSilk); if (ro) ro.observe($('#visageSilk')); }
    }
  });
  function pickImp(key, focus) {
    if (!IMP[key]) return;
    visStyle = key;
    visage.setAttribute('data-style', key);
    impBtns.forEach(function (b) {
      var on = b.getAttribute('data-style') === key;
      b.classList.toggle('is-on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1;
      if (on && focus) b.focus();
      if (on && b.scrollIntoView && window.matchMedia('(max-width: 767px)').matches && focus !== null) {
        var list = b.parentNode; list.scrollTo({ left: b.offsetLeft - (list.clientWidth - b.offsetWidth) / 2, behavior: still ? 'auto' : 'smooth' });
      }
    });
    props.forEach(function (p) { var on = p.getAttribute('data-style') === key; p.hidden = !on; p.classList.toggle('is-on', on); });
    if (visFig) visFig.setStyle(key, still ? 0 : 1700);
    if (visSilk && visSilk.ok) visSilk.setColors(IMP[key].silk, still ? 0 : 1700);
  }
  impBtns.forEach(function (b, i) {
    b.addEventListener('click', function () { pickImp(b.getAttribute('data-style'), false); });
    b.addEventListener('keydown', function (e) {
      var d = (e.key === 'ArrowDown' || e.key === 'ArrowRight') ? 1 : (e.key === 'ArrowUp' || e.key === 'ArrowLeft') ? -1 : 0;
      if (!d) return;
      e.preventDefault();
      pickImp(ORDER[(i + d + ORDER.length) % ORDER.length], true);
    });
  });

  /* ---------- スタイリストの絵（動かさず描くだけ） ---------- */
  later('#stylist', function () { $$('.person__fig').forEach(function (cv, i) {
    if (!Figure) return;
    var f = new Figure(cv, { style: cv.getAttribute('data-fig'), grow: !still, sway: false, seed: 31 + i * 7, strands: 190, bangs: 48 });
    var idle = { start: function () {}, stop: function () {}, finish: function () { f.finish(); }, resize: function (w, h) { f.resize(w, h); } };
    addActor(cv, idle, function () { if (still) f.finish(); else f.reveal(); });
    if (ro) ro.observe(cv);
  }); });

  /* ---------- 現れる動き ---------- */
  $$('[data-reveal]').forEach(function (el) {
    var sibs = $$(':scope > [data-reveal]', el.parentNode), i = sibs.indexOf(el);
    if (i > 0) el.style.setProperty('--d', Math.min(i * 0.09, 0.45) + 's');
  });
  if ('IntersectionObserver' in window) {
    var revealer = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('is-in'); revealer.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.12 });
    $$('[data-reveal], [data-lines], .map').forEach(function (el) { revealer.observe(el); });
  } else {
    $$('[data-reveal], [data-lines], .map').forEach(function (el) { el.classList.add('is-in'); });
  }

  /* ---------- スクロールに合わせる物 ---------- */
  var hd = $('#hd'), dock = $('#dock'), flow = $('#flow'), reserveSec = $('#reserve');
  var pars = $$('[data-parallax]'), lastY = 0, ticking = false, drawerOpen = false;
  var navLinks = $$('#navPc a');
  var sections = NAV.map(function (n) { return doc.getElementById(n.href.slice(1)); }).filter(Boolean);
  if (dock) dock.hidden = false;

  function onScroll() {
    ticking = false;
    var y = window.scrollY, vh = window.innerHeight;
    hd.classList.toggle('is-solid', y > 24);
    if (!drawerOpen) {
      if (y > lastY + 4 && y > 480) hd.classList.add('is-hidden');
      else if (y < lastY - 4 || y <= 480) hd.classList.remove('is-hidden');
    }
    lastY = y;
    if (!still) {
      pars.forEach(function (el) {
        var r = el.parentNode.getBoundingClientRect();
        if (r.bottom < -200 || r.top > vh + 200) return;
        var k = parseFloat(el.getAttribute('data-parallax')) || 0;
        el.style.transform = 'translate3d(0,' + ((r.top + r.height / 2 - vh / 2) * k).toFixed(1) + 'px,0)';
      });
      if (flow) { var fr = flow.getBoundingClientRect(); flow.style.setProperty('--p', clamp((vh * 0.82 - fr.top) / (vh * 0.5), 0, 1).toFixed(3)); }
    }
    if (dock) {
      var rr = reserveSec.getBoundingClientRect();
      dock.classList.toggle('is-on', y > vh * 0.7 && !(rr.top < vh * 0.7 && rr.bottom > vh * 0.3));
    }
    var cur = null;
    sections.forEach(function (s) { if (s.getBoundingClientRect().top < vh * 0.4) cur = s.id; });
    navLinks.forEach(function (a) { if (a.getAttribute('href') === '#' + cur) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); });
  }
  window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  window.addEventListener('resize', function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } });
  ticking = true; requestAnimationFrame(onScroll);

  /* ---------- スマホのメニュー ---------- */
  var drawer = $('#drawer'), menuBtn = $('#menuToggle');
  function setDrawer(open) {
    drawerOpen = open;
    menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    doc.body.classList.toggle('is-locked', open);
    if (open) { drawer.hidden = false; hd.classList.remove('is-hidden'); hd.classList.add('is-solid'); requestAnimationFrame(function () { drawer.classList.add('is-open'); }); }
    else { drawer.classList.remove('is-open'); setTimeout(function () { if (!drawerOpen) drawer.hidden = true; }, still ? 0 : 420); onScroll(); }
  }
  menuBtn.addEventListener('click', function () { setDrawer(!drawerOpen); });
  drawer.addEventListener('click', function (e) { if (e.target.closest('a')) setDrawer(false); });
  doc.addEventListener('keydown', function (e) { if (e.key === 'Escape' && drawerOpen) { setDrawer(false); menuBtn.focus(); } });

  /* ---------- お知らせ・架空のボタン ---------- */
  var toast = $('#toast'), toastTimer = 0;
  function say(msg) {
    toast.textContent = msg; toast.classList.add('is-on');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { toast.classList.remove('is-on'); }, 3200);
  }
  $$('[data-demo]').forEach(function (b) {
    b.addEventListener('click', function () {
      say(b.getAttribute('data-demo') === 'tel' ? '架空の番号のため発信しません。' : '架空の店のため地図アプリは開きません。');
    });
  });

  /* ---------- 設計メモ ---------- */
  var memo = $('#memo'), memoOpen = $('#memoOpen');
  if (memo && memo.showModal) {
    memoOpen.addEventListener('click', function () { memo.showModal(); });
    $('#memoClose').addEventListener('click', function () { memo.close(); });
    memo.addEventListener('click', function (e) { if (e.target === memo) memo.close(); });
    memo.addEventListener('close', function () { memoOpen.focus(); });
  } else if (memoOpen) { memoOpen.hidden = true; }

  /* ---------- 予約のデモ ---------- */
  var MENUS = [
    { id: 'course', name: 'なりたい私コース', min: 180, price: 19800 },
    { id: 'cut', name: 'カット', min: 60, price: 7700 },
    { id: 'cut-color', name: 'カット＋カラー', min: 150, price: 15400 },
    { id: 'cut-hl', name: 'カット＋ハイライトカラー', min: 180, price: 20900 },
    { id: 'cut-perm', name: 'カット＋パーマ', min: 150, price: 16500 },
    { id: 'cut-perm-color', name: 'カット＋パーマ＋カラー', min: 240, price: 24200 },
    { id: 'cut-straight', name: 'カット＋縮毛矯正', min: 210, price: 24200 },
    { id: 'treat', name: '艶トリートメント', min: 30, price: 4400 },
    { id: 'spa', name: 'ヘッドスパ', min: 40, price: 5500 },
    { id: 'ask', name: '相談してから決める', min: 20, price: 0 }
  ];
  var STAFF = [{ id: 'any', name: '指名なし' }, { id: 'shiho', name: '志保' }, { id: 'rei', name: '玲' }, { id: 'mao', name: '真央' }];
  var WD = ['日', '月', '火', '水', '木', '金', '土'];
  var st = { menu: 'course', day: null, time: null, staff: 'any', imp: null };
  var elMenu = $('#rfMenu'), elDays = $('#rfDays'), elSlots = $('#rfSlots'), elStaff = $('#rfStaff'), elImp = $('#rfImp');
  var yen = function (n) { return '¥' + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); };
  var dur = function (m) { var h = Math.floor(m / 60), r = m % 60; return (h ? h + '時間' : '') + (r ? r + '分' : ''); };
  var hhmm = function (m) { return Math.floor(m / 60) + ':' + ('0' + (m % 60)).slice(-2); };
  function hash(s) { var x = 2166136261; for (var i = 0; i < s.length; i++) { x ^= s.charCodeAt(i); x = Math.imul(x, 16777619); } return (x >>> 0) / 4294967296; }
  function byId(list, id) { for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i]; return null; }

  var DAYS = [];
  (function () {
    var now = new Date();
    for (var i = 1; i <= 7; i++) {
      var d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i), wd = d.getDay();
      var weekend = wd === 0 || wd === 6;
      DAYS.push({ key: d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate(), m: d.getMonth() + 1, d: d.getDate(), wd: wd, closed: wd === 2, open: weekend ? 9 : 10, close: weekend ? 19 : 20 });
    }
    for (var k = 0; k < DAYS.length; k++) if (!DAYS[k].closed) { st.day = DAYS[k].key; break; }
  })();
  function dayOf(key) { for (var i = 0; i < DAYS.length; i++) if (DAYS[i].key === key) return DAYS[i]; return null; }

  function radio(tag, cls, checked, html, onPick) {
    var b = doc.createElement('button');
    b.type = 'button'; b.className = cls; b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', checked ? 'true' : 'false');
    b.innerHTML = html; b.addEventListener('click', onPick);
    tag.appendChild(b); return b;
  }
  function drawMenu() {
    elMenu.textContent = '';
    MENUS.forEach(function (m) {
      var sub = m.price ? dur(m.min) + '・' + yen(m.price) : 'カウンセリング20分・無料';
      radio(elMenu, 'chip', st.menu === m.id, '<span>' + m.name + '</span><small>' + sub + '</small>', function () { st.menu = m.id; drawMenu(); drawSlots(); drawSum(); });
    });
  }
  function drawDays() {
    elDays.textContent = '';
    DAYS.forEach(function (d) {
      var b = radio(elDays, 'day', st.day === d.key, '<span>' + WD[d.wd] + '</span><b>' + d.d + '</b><span>' + (d.closed ? '定休' : d.m + '月') + '</span>', function () { st.day = d.key; drawDays(); drawSlots(); drawSum(); });
      if (d.closed) b.disabled = true;
    });
  }
  function slotState(d, h, m) {
    if (h * 60 + m.min > d.close * 60) return 'na';
    return hash(d.key + '|' + h + '|' + st.staff) < 0.3 ? 'ng' : 'ok';
  }
  function drawSlots() {
    var d = dayOf(st.day), m = byId(MENUS, st.menu);
    elSlots.textContent = '';
    if (!d) return;
    var still_ok = false;
    for (var h = d.open; h < d.close; h++) {
      (function (h) {
        var state = slotState(d, h, m), t = h * 60;
        if (st.time === t && state === 'ok') still_ok = true;
        var b = radio(elSlots, 'slot', st.time === t && state === 'ok', hhmm(t), function () { st.time = t; drawSlots(); drawSum(); $('#sumErr').textContent = ''; });
        b.setAttribute('data-state', state);
        b.setAttribute('aria-label', hhmm(t) + (state === 'ok' ? ' 空きあり' : state === 'ng' ? ' 満席' : ' 閉店までに終わりません'));
        if (state !== 'ok') b.disabled = true;
      })(h);
    }
    if (!still_ok) st.time = null;
  }
  function drawStaff() {
    elStaff.textContent = '';
    STAFF.forEach(function (s) { radio(elStaff, 'chip', st.staff === s.id, '<span>' + s.name + '</span>', function () { st.staff = s.id; drawStaff(); drawSlots(); drawSum(); }); });
  }
  function drawImp() {
    elImp.textContent = '';
    ORDER.forEach(function (k) {
      radio(elImp, 'chip', st.imp === k, '<span>' + IMP[k].jp + '</span>', function () { st.imp = st.imp === k ? null : k; drawImp(); drawSum(); });
    });
  }
  function summary() {
    var m = byId(MENUS, st.menu), d = dayOf(st.day), s = byId(STAFF, st.staff);
    return {
      menu: m.name + '（' + (m.price ? dur(m.min) : 'カウンセリング20分') + '）',
      when: d && st.time !== null ? d.m + '月' + d.d + '日（' + WD[d.wd] + '）' + hhmm(st.time) : (d ? d.m + '月' + d.d + '日（' + WD[d.wd] + '）時間は未選択' : '—'),
      end: st.time !== null ? hhmm(st.time + m.min) + 'ごろ' : '—',
      staff: s.name,
      imp: st.imp ? IMP[st.imp].jp : '当日に相談',
      total: m.price ? yen(m.price) : '相談のあとで'
    };
  }
  function drawSum() {
    var s = summary();
    $('#sumMenu').textContent = s.menu; $('#sumWhen').textContent = s.when; $('#sumEnd').textContent = s.end;
    $('#sumStaff').textContent = s.staff; $('#sumImp').textContent = s.imp; $('#sumTotal').textContent = s.total;
  }
  function drawAll() { drawMenu(); drawDays(); drawSlots(); drawStaff(); drawImp(); drawSum(); }
  var formReady = false;
  later('#reserve', function () { if (elMenu && !formReady) { formReady = true; drawAll(); } });

  /* ほかの章から予約欄へ内容を渡す */
  var vr = $('#visageReserve');
  if (vr) vr.addEventListener('click', function () { st.imp = visStyle; st.menu = IMP[visStyle].menu; backToForm(); drawAll(); say('「' + IMP[visStyle].jp + '」を予約欄に入れました。'); });
  $$('[data-pick-menu]').forEach(function (a) { a.addEventListener('click', function () { st.menu = a.getAttribute('data-pick-menu'); backToForm(); drawAll(); }); });
  $$('[data-pick-staff]').forEach(function (a) { a.addEventListener('click', function () { st.staff = a.getAttribute('data-pick-staff'); backToForm(); drawAll(); }); });

  var form = $('#reserveForm'), done = $('#done'), nameIn = $('#rfName'), mailIn = $('#rfEmail');
  function fieldErr(input, id, msg) { $('#' + id).textContent = msg; if (msg) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid'); }
  function backToForm() { reserveSec.classList.remove('is-done'); done.hidden = true; }
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();                                   /* デモ：どこにも送らない */
      var bad = null, sumErr = $('#sumErr');
      sumErr.textContent = '';
      if (st.time === null) { sumErr.textContent = '時間を選んでください。'; bad = $('#rfSlots button:not(:disabled)') || elSlots; }
      var nm = nameIn.value.trim(), ml = mailIn.value.trim();
      fieldErr(nameIn, 'rfNameErr', nm ? '' : 'お名前を入れてください。');
      fieldErr(mailIn, 'rfEmailErr', /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(ml) ? '' : 'メールアドレスの形を確かめてください。');
      if (!bad && !nm) bad = nameIn;
      if (!bad && nameIn.getAttribute('aria-invalid') !== 'true' && mailIn.getAttribute('aria-invalid') === 'true') bad = mailIn;
      if (!bad && mailIn.getAttribute('aria-invalid') === 'true') bad = mailIn;
      if (bad) { if (!sumErr.textContent) sumErr.textContent = '入力を確かめてください。'; bad.focus(); return; }
      var s = summary(), list = $('#doneList');
      list.textContent = '';
      [['メニュー', s.menu], ['日時', s.when], ['終わる時刻', s.end], ['担当', s.staff], ['印象', s.imp], ['総額', s.total + '（税込・架空）'], ['お名前', nm + ' さま']].forEach(function (r) {
        var div = doc.createElement('div'), dt = doc.createElement('dt'), dd = doc.createElement('dd');
        dt.textContent = r[0]; dd.textContent = r[1]; div.appendChild(dt); div.appendChild(dd); list.appendChild(div);
      });
      reserveSec.classList.add('is-done'); done.hidden = false;
      done.focus({ preventScroll: true });
      reserveSec.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
    });
    [nameIn, mailIn].forEach(function (inp) { inp.addEventListener('input', function () { if (inp.getAttribute('aria-invalid')) fieldErr(inp, inp.id + 'Err', ''); }); });
    $('#doneBack').addEventListener('click', function () { backToForm(); nameIn.focus(); });
  }
})();
