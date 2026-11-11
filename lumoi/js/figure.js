/* LUMOI — 鏡の中の横顔と髪（canvas 2D・画像は使わない）
   髪は1本ずつ曲線で描く。長さ・うねり・毛先・前髪・色を数値で持ち、印象が変わると数値をなめらかに移す。 */
(function (global) {
  'use strict';

  var W = 400, H = 560;

  /* 印象ごとの髪の設計（すべて絵のための数値） */
  var STYLES = {
    douce:  { len: 426, frontLen: 410, frontX: 180, backX: 326, wave: 9,   freq: 1.3,  curl: 24,  vol: 1.0,  bang: 0.62, layer: 16, nape: 0,    hl: 0.10, arc: 12,
              root: '#7d5f4d', mid: '#ad8a72', tip: '#d8bca3', shine: '#f6e7d6' },
    nette:  { len: 314, frontLen: 332, frontX: 172, backX: 296, wave: 0.6, freq: 1.0,  curl: 8,   vol: 0.94, bang: 0.0,  layer: 2,  nape: 0.4,  hl: 0.04, arc: 0,
              root: '#2b272d', mid: '#48424b', tip: '#67616d', shine: '#cfc9d6' },
    eclat:  { len: 516, frontLen: 500, frontX: 172, backX: 348, wave: 15,  freq: 2.2,  curl: 10,  vol: 1.16, bang: 0.0,  layer: 16, nape: 0,    hl: 0.14, arc: 12,
              root: '#573838', mid: '#8a5957', tip: '#c18f87', shine: '#f4d6cd' },
    claire: { len: 498, frontLen: 462, frontX: 182, backX: 322, wave: 2.4, freq: 1.0,  curl: -5,  vol: 0.97, bang: 0.42, layer: 30, nape: 0,    hl: 0.30, arc: 16,
              root: '#69665a', mid: '#9a9483', tip: '#cfc9b7', shine: '#f6f3e6' },
    legere: { len: 290, frontLen: 262, frontX: 190, backX: 270, wave: 2.5, freq: 1.3,  curl: 5,   vol: 1.06, bang: 0.9,  layer: 12, nape: 1,    hl: 0.16, arc: -6,
              root: '#775638', mid: '#a8804d', tip: '#d9b279', shine: '#f9e6c0' }
  };
  var NUM = ['len', 'frontLen', 'frontX', 'backX', 'wave', 'freq', 'curl', 'vol', 'bang', 'layer', 'nape', 'hl', 'arc'];
  var COL = ['root', 'mid', 'tip', 'shine'];

  function hex(h) { var n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function mix(a, b, t) { return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]; }
  function rgba(c, a) { return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + a.toFixed(3) + ')'; }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function smooth(t) { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); }
  function ease(t) { t = clamp(t, 0, 1); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  function resolve(s) {
    var o = {};
    NUM.forEach(function (k) { o[k] = s[k]; });
    COL.forEach(function (k) { o[k] = hex(s[k]); });
    return o;
  }
  function blend(a, b, t) {
    var o = {};
    NUM.forEach(function (k) { o[k] = lerp(a[k], b[k], t); });
    COL.forEach(function (k) { o[k] = mix(a[k], b[k], t); });
    return o;
  }

  /* 頭の上の生えぎわの線（額の生えぎわ → てっぺん → つむじ） */
  var F = [151, 103], TOP = [203, 27], K = [289, 108];
  function rootPt(u) {
    var a = (1 - u) * (1 - u), b = 2 * u * (1 - u), c = u * u;
    return [a * F[0] + b * TOP[0] + c * K[0], a * F[1] + b * TOP[1] + c * K[1]];
  }
  function bez(p0, p1, p2, p3, s) {
    var m = 1 - s, a = m * m * m, b = 3 * m * m * s, c = 3 * m * s * s, d = s * s * s;
    return [a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]];
  }

  var SEG = 20;

  /* 顔と体の線（左向きの横顔） */
  var PATHS = {
    skin: 'M152 100 C136 118 126 140 125 160 C124 170 126 178 131 186 C126 198 114 212 105 224 C102 229 106 234 114 235 C119 236 123 237 124 240 C124 244 119 247 118 251 C117 255 121 257 126 258 C121 260 118 264 120 269 C121 273 127 275 128 279 C129 286 122 292 124 299 C126 307 135 312 146 312 C151 312 156 312 160 314 C162 338 168 362 172 384 C174 402 160 424 128 446 C108 460 96 486 92 560 L398 560 C396 500 388 466 372 452 C344 426 300 414 280 394 C266 372 260 330 262 290 C292 262 306 206 300 160 C294 116 258 86 215 84 C188 84 166 90 152 100 Z',
    face: 'M152 100 C136 118 126 140 125 160 C124 170 126 178 131 186 C126 198 114 212 105 224 C102 229 106 234 114 235 C119 236 123 237 124 240 C124 244 119 247 118 251 C117 255 121 257 126 258 C121 260 118 264 120 269 C121 273 127 275 128 279 C129 286 122 292 124 299 C126 307 135 312 146 312 C164 312 184 305 200 292',
    neckFront: 'M160 314 C162 338 168 362 172 384 C174 402 160 424 128 446 C110 459 98 482 93 540',
    neckBack: 'M262 292 C260 330 266 372 280 394 C300 414 344 426 372 452 C386 464 394 492 397 540',
    brow: 'M134 171 C142 164 155 163 167 170',
    eye: 'M139 191 C145 197 155 197 162 190',
    lash1: 'M141 193 L137 197', lash2: 'M146 196 L143 201', lash3: 'M152 196.5 L151 202',
    lip: 'M118 251 C121 254 124 256.5 128 258 C124 260.5 121 265 120 269 C116 265 115.5 256 118 251 Z',
    nostril: 'M117 232 C119 230 121 230.5 122 232',
    garment: 'M124 449 C170 470 250 452 300 410 C330 420 356 436 372 452 C388 466 396 500 398 560 L92 560 C96 500 106 462 124 449 Z',
    garmentLine: 'M124 449 C170 470 250 452 300 410'
  };

  var SMALL = !!(global.matchMedia && global.matchMedia('(max-width: 767px)').matches);

  function Figure(canvas, opts) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    var small = SMALL, wk = small ? 1.28 : 1;
    this.o = Object.assign({ strands: small ? 168 : 230, bangs: small ? 48 : 64, style: 'douce', seed: 11, align: 0.5, zoom: 1, offsetY: 0, grow: true, sway: true }, opts || {});
    var r = rng(this.o.seed), i, n = this.o.strands, m = this.o.bangs;
    this.S = [];
    for (i = 0; i < n; i++) this.S.push({ t: i / (n - 1), j: [r() * 2 - 1, r() * 2 - 1, r() * 2 - 1, r() * 2 - 1], w: (1.1 + r() * 1.8) * wk, a: 0.6 + r() * 0.36, l: r(), h: r() });
    /* 後ろの毛から描いて手前の毛を上に重ねる。少しだけ順番を乱して束に見せる */
    this.order = this.S.slice().sort(function (a, b) { return (b.t + b.j[2] * 0.08) - (a.t + a.j[2] * 0.08); });
    this.B = [];
    for (i = 0; i < m; i++) this.B.push({ t: i / (m - 1), j: [r() * 2 - 1, r() * 2 - 1, r() * 2 - 1], w: (1.2 + r() * 1.6) * wk, a: 0.58 + r() * 0.36, l: r(), rank: r(), h: r() });
    this.paths = {};
    for (var k in PATHS) this.paths[k] = new Path2D(PATHS[k]);
    this.from = this.to = this.cur = resolve(STYLES[this.o.style]);
    this.styleName = this.o.style;
    this.mixT = 1; this.mixDur = 1;
    this.grow = this.o.grow ? 0 : 1;
    this.time = 0; this.last = 0; this.raf = 0; this.running = false; this.dirty = true;
    this._pts = new Float32Array((SEG + 1) * 2);
    this.cw = 0; this.ch = 0; this.ver = 1; this.cost = 4; this.lod = 1;
  }

  Figure.STYLES = STYLES;

  /* 大きさを合わせる。幅と高さを渡されたときは画面を測り直さない */
  Figure.prototype._measure = function (cssW, cssH) {
    if (!(cssW > 0 && cssH > 0)) { var rect = this.canvas.getBoundingClientRect(); cssW = rect.width; cssH = rect.height; }
    if (!(cssW > 0 && cssH > 0)) return;
    var dpr = Math.min(global.devicePixelRatio || 1, 2);
    var w = Math.max(1, Math.round(cssW * dpr)), h = Math.max(1, Math.round(cssH * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; this.ver++; }
    this.cw = w; this.ch = h;
    var sc = Math.max(w / W, h / H) * this.o.zoom;
    this.scale = sc;
    this.ox = (w - W * sc) * this.o.align;
    this.oy = this.o.offsetY * sc;
  };
  Figure.prototype.resize = function (cssW, cssH) { this._measure(cssW, cssH); if (!this.running) this.draw(); };

  Figure.prototype.setStyle = function (name, ms) {
    if (!STYLES[name]) return;
    this.from = this.cur; this.to = resolve(STYLES[name]); this.styleName = name;
    if (!ms) { this.cur = this.to; this.mixT = 1; this.ver++; if (!this.running) this.draw(); return; }
    this.mixT = 0; this.mixDur = ms / 1000;
    if (!this.running) this._kick();
  };

  /* 動きを止めているあいだでも、変化と描き込みだけは最後まで進める */
  Figure.prototype._kick = function () {
    var self = this;
    if (this.raf) return;
    this.last = 0;
    var step = function (now) {
      self.raf = 0;
      var gapMs = self.last ? now - self.last : 1e3, dt = Math.min(0.1, gapMs / 1000);
      /* ゆれているだけのあいだは毎秒30コマまで。遅い端末では描く間隔をさらに空ける。変化の途中も描く時間の1.5倍は空ける */
      var changing = self.mixT < 1 || self.grow < 1;
      var need = changing ? self.cost * 1.5 : Math.max(30, self.cost * 4);
      if (self.last && gapMs < need) { self.raf = global.requestAnimationFrame(step); return; }
      if (!self.last) dt = 0.016;
      self.last = now;
      var busy = self._advance(dt, self.running);
      var t0 = global.performance.now();
      self.draw();
      self.cost += (global.performance.now() - t0 - self.cost) * 0.2;
      /* 1コマに時間がかかる端末では、髪を1本おきにして太く描く */
      if (self.lod === 1 && self.cost > 13) { self.lod = 2; self.cost *= 0.55; } else if (self.lod === 2 && self.cost < 3.5) { self.lod = 1; self.cost *= 1.8; }
      if (self.running || busy) self.raf = global.requestAnimationFrame(step);
    };
    this.raf = global.requestAnimationFrame(step);
  };

  Figure.prototype._advance = function (dt, sway) {
    var busy = false;
    if (sway && this.o.sway) this.time += dt;
    if (this.mixT < 1) { this.mixT = Math.min(1, this.mixT + dt / this.mixDur); this.cur = blend(this.from, this.to, ease(this.mixT)); this.ver++; busy = true; }
    if (this.grow < 1) { this.grow = Math.min(1, this.grow + dt / 2.1); busy = true; }
    return busy;
  };

  Figure.prototype.start = function () { if (this.running) return; this.running = true; this._kick(); };
  Figure.prototype.stop = function () { this.running = false; };
  Figure.prototype.reveal = function () { this._kick(); };
  Figure.prototype.finish = function () { this.grow = 1; this.mixT = 1; this.cur = this.to; this.ver++; this.draw(); };

  /* 髪1本の点の列を作る */
  Figure.prototype._strand = function (st, P, time, plain) {
    var t = st.t, j = plain ? [0, 0, 0, 0] : st.j, out = this._pts;
    var R = rootPt(0.05 + 0.95 * Math.pow(t, 0.9));
    var ex = lerp(P.frontX, P.backX, t) + j[0] * 5;
    var ey = lerp(P.frontLen, P.len, smooth(t)) + Math.sin(3.1416 * t) * P.arc - Math.abs(j[1]) * P.layer;
    var drop = ey - R[1];
    var p1 = [lerp(204, K[0] + 34 * P.vol, t) + j[2] * 4, lerp(114, K[1] + 24, t) + j[3] * 3];
    var p2 = [ex + lerp(20, 6 + 30 * P.nape, t) * P.vol, ey - drop * lerp(0.46, lerp(0.64, 0.42, P.nape), t)];
    var p3 = [ex, ey];
    var ph = t * 1.5 + j[0] * 0.05, dir = ex < 232 ? 1 : -1;
    for (var k = 0; k <= SEG; k++) {
      var s = k / SEG, p = bez(R, p1, p2, p3, s);
      var env = smooth((s - 0.3) / 0.36);
      var x = p[0] + P.wave * env * Math.sin(6.2832 * (P.freq * s + ph) + time * 0.5);
      if (s > 0.72) { var e = (s - 0.72) / 0.28; x += P.curl * e * e * dir; }
      x += Math.sin(time * 0.62 + t * 3.1 + j[1]) * 2.6 * env * s;
      out[k * 2] = x; out[k * 2 + 1] = p[1];
    }
    return out;
  };

  /* 前髪1本の点の列。bang が小さいと後ろへ流した毛に、大きいと額にかかる毛になる */
  Figure.prototype._bang = function (st, P, time) {
    var t = st.t, j = st.j, out = this._pts;
    var w = smooth((P.bang * 1.25 - st.rank) / 0.25 + 0.5);
    var R = rootPt(0.08 + 0.34 * t);
    var sEx = P.frontX + j[0] * 6 + t * 10, sEy = P.frontLen - Math.abs(j[1]) * P.layer - 6;
    var sdrop = sEy - R[1];
    var s1 = [204 + j[2] * 5, 112 + j[1] * 4], s2 = [sEx + 22 * P.vol, sEy - sdrop * 0.46];
    var bEx = 124 + 58 * t + j[0] * 3, bEy = 163 + 8 * t + 54 * smooth((t - 0.6) / 0.4) + j[1] * 3;
    var b1 = [R[0] - 24 - 8 * (1 - t), R[1] + 8], b2 = [bEx - 7 + 10 * t, bEy - 36];
    var p1 = [lerp(s1[0], b1[0], w), lerp(s1[1], b1[1], w)];
    var p2 = [lerp(s2[0], b2[0], w), lerp(s2[1], b2[1], w)];
    var p3 = [lerp(sEx, bEx, w), lerp(sEy, bEy, w)];
    for (var k = 0; k <= SEG; k++) {
      var s = k / SEG, p = bez(R, p1, p2, p3, s);
      var env = smooth((s - 0.3) / 0.36) * (1 - w);
      var x = p[0] + P.wave * env * Math.sin(6.2832 * (P.freq * s + 0.1) + time * 0.5);
      if (s > 0.8) { var e = (s - 0.8) / 0.2; x += P.curl * e * e * (1 - w); }
      x += Math.sin(time * 0.7 + t * 4 + j[1]) * 1.2 * s * (0.4 + 0.6 * (1 - w));
      out[k * 2] = x; out[k * 2 + 1] = p[1];
    }
    return out;
  };

  Figure.prototype._stroke = function (ctx, pts, upto) {
    var n = Math.max(2, Math.round(SEG * upto));
    ctx.beginPath();
    ctx.moveTo(pts[0], pts[1]);
    for (var k = 1; k < n; k++) {
      var mx = (pts[k * 2] + pts[k * 2 + 2]) / 2, my = (pts[k * 2 + 1] + pts[k * 2 + 3]) / 2;
      ctx.quadraticCurveTo(pts[k * 2], pts[k * 2 + 1], mx, my);
    }
    ctx.lineTo(pts[n * 2], pts[n * 2 + 1]);
    ctx.stroke();
  };

  Figure.prototype.draw = function () {
    if (!this.cw) { this._measure(); if (!this.cw) return; }
    var ctx = this.ctx, P = this.cur, time = this.time, g = this.grow, i, k, pts, st;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.cw, this.ch);
    ctx.setTransform(this.scale, 0, 0, this.scale, this.ox, this.oy);
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';

    var inA = smooth(g * 2.2);

    /* 肌 */
    var sg = ctx.createLinearGradient(110, 90, 300, 480);
    sg.addColorStop(0, 'rgba(253,246,238,' + (0.96 * inA).toFixed(3) + ')');
    sg.addColorStop(1, 'rgba(244,229,216,' + (0.96 * inA).toFixed(3) + ')');
    ctx.fillStyle = sg; ctx.fill(this.paths.skin);
    /* 頬の赤み */
    var cg = ctx.createRadialGradient(168, 236, 2, 168, 236, 40);
    cg.addColorStop(0, 'rgba(214,150,138,' + (0.16 * inA).toFixed(3) + ')'); cg.addColorStop(1, 'rgba(214,150,138,0)');
    ctx.fillStyle = cg; ctx.fillRect(120, 190, 100, 100);
    /* 服 */
    var gg = ctx.createLinearGradient(0, 410, 0, 560);
    gg.addColorStop(0, 'rgba(255,253,250,' + (0.95 * inA).toFixed(3) + ')'); gg.addColorStop(1, 'rgba(240,232,224,' + (0.95 * inA).toFixed(3) + ')');
    ctx.fillStyle = gg; ctx.fill(this.paths.garment);

    /* 線 */
    ctx.strokeStyle = 'rgba(74,54,56,' + (0.82 * inA).toFixed(3) + ')';
    ctx.lineWidth = 1.25;
    ctx.stroke(this.paths.face); ctx.stroke(this.paths.neckFront); ctx.stroke(this.paths.neckBack);
    ctx.lineWidth = 1.0; ctx.strokeStyle = 'rgba(74,54,56,' + (0.5 * inA).toFixed(3) + ')';
    ctx.stroke(this.paths.garmentLine); ctx.stroke(this.paths.nostril);
    ctx.strokeStyle = 'rgba(74,54,56,' + (0.86 * inA).toFixed(3) + ')';
    ctx.lineWidth = 1.5; ctx.stroke(this.paths.eye);
    ctx.lineWidth = 1.0; ctx.stroke(this.paths.lash1); ctx.stroke(this.paths.lash2); ctx.stroke(this.paths.lash3);
    ctx.strokeStyle = rgba(mix(P.root, [74, 54, 56], 0.4), 0.7 * inA); ctx.lineWidth = 2.2; ctx.stroke(this.paths.brow);
    ctx.fillStyle = 'rgba(190,112,108,' + (0.62 * inA).toFixed(3) + ')'; ctx.fill(this.paths.lip);

    /* 髪のかたまり（下地） */
    var top = 60, bottom = Math.max(P.len, P.frontLen);
    var mg = ctx.createLinearGradient(0, top, 0, bottom);
    mg.addColorStop(0, rgba(P.root, 0.96 * inA));
    mg.addColorStop(0.55, rgba(mix(P.root, P.mid, 0.7), 0.94 * inA));
    mg.addColorStop(1, rgba(mix(P.mid, P.tip, 0.45), 0.9 * inA));
    ctx.fillStyle = mg;
    ctx.beginPath();
    var ghost = { t: 0, j: [0, 0, 0, 0] };
    pts = this._strand(ghost, P, time, true);
    ctx.moveTo(pts[0], pts[1]);
    for (k = 1; k <= SEG; k++) ctx.lineTo(pts[k * 2], pts[k * 2 + 1]);
    for (i = 1; i <= 20; i++) { ghost.t = i / 20; pts = this._strand(ghost, P, time, true); ctx.lineTo(pts[SEG * 2], pts[SEG * 2 + 1] - P.layer * 1.0 - 4 - 3 * Math.sin(i * 2.4)); }
    for (k = SEG - 1; k >= 0; k--) ctx.lineTo(pts[k * 2], pts[k * 2 + 1]);
    for (i = 19; i >= 0; i--) { var rp = rootPt(0.05 + 0.95 * Math.pow(i / 20, 0.9)); ctx.lineTo(rp[0], rp[1]); }
    ctx.closePath(); ctx.fill();

    /* 髪（1本ずつ） */
    var S = this.order, lod = this.lod;
    this._k = lod === 2 ? 1.75 : 1;
    for (i = 0; i < S.length; i += lod) {
      st = S[i];
      var prog = clamp(g * 1.7 - (1 - st.t) * 0.5 - st.l * 0.2, 0, 1);
      if (prog <= 0.02) continue;
      pts = this._strand(st, P, time, false);
      this._paint(ctx, pts, st, P, ease(prog));
    }
    var Bn = this.B;
    for (i = 0; i < Bn.length; i += lod) {
      st = Bn[i];
      var pb = clamp(g * 1.7 - 0.55 - st.l * 0.2, 0, 1);
      if (pb <= 0.02) continue;
      pts = this._bang(st, P, time);
      this._paint(ctx, pts, st, P, ease(pb));
    }
  };

  Figure.prototype._paint = function (ctx, pts, st, P, upto) {
    if (st.cv !== this.ver) {                       /* 色の帯は、色か大きさが変わったときだけ作り直す（毎コマ作ると重い） */
      var light = st.h < P.hl;                      /* 細い明るい筋 */
      var c0 = P.root, c1 = P.mid, c2 = P.tip;
      var lj = (st.l - 0.5) * 0.36;
      var a = st.a * (light ? 1 : 0.92);
      var rootC = lj > 0 ? mix(c0, c1, lj * 1.6) : mix(c0, [20, 14, 16], -lj * 0.7);
      var midC = light ? mix(c1, P.shine, 0.55) : (lj > 0 ? mix(c1, c2, lj * 1.5) : mix(c1, c0, -lj * 1.4));
      var tipC = light ? mix(c2, P.shine, 0.7) : mix(c2, P.shine, clamp(lj, 0, 1));
      var gr = ctx.createLinearGradient(pts[0], pts[1], pts[SEG * 2], pts[SEG * 2 + 1]);
      gr.addColorStop(0, rgba(rootC, a));
      gr.addColorStop(0.235, rgba(mix(midC, P.shine, 0.3 + st.l * 0.5), Math.min(1, a + 0.12)));
      gr.addColorStop(0.38, rgba(midC, a));
      gr.addColorStop(0.9, rgba(tipC, a * 0.95));
      gr.addColorStop(1, rgba(tipC, a * lerp(0.9, 0.4, clamp(P.layer / 26, 0, 1))));
      st.g = gr; st.lw = light ? st.w * 0.8 : st.w; st.cv = this.ver;
    }
    ctx.strokeStyle = st.g; ctx.lineWidth = st.lw * this._k;
    this._stroke(ctx, pts, upto);
  };

  global.LumoiFigure = Figure;
})(window);
