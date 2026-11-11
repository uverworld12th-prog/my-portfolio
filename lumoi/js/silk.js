/* LUMOI — 絹のような光（WebGL・画像は使わない）
   小さく描いて引きのばす。見えていないときは止める。WebGL が使えない端末では CSS の背景がそのまま見える。 */
(function (global) {
  'use strict';

  var VERT = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
  var FRAG = [
    'precision mediump float;',
    'uniform vec2 uR;uniform float uT;uniform vec3 uA;uniform vec3 uB;uniform vec3 uC;uniform vec3 uD;uniform vec2 uP;',
    'vec3 pm(vec3 x){return mod(((x*34.0)+1.0)*x,289.0);}',
    'float sn(vec2 v){const vec4 C=vec4(0.211324865405187,0.366025403784439,-0.577350269189626,0.024390243902439);',
    ' vec2 i=floor(v+dot(v,C.yy));vec2 x0=v-i+dot(i,C.xx);vec2 i1=(x0.x>x0.y)?vec2(1.0,0.0):vec2(0.0,1.0);',
    ' vec4 x12=x0.xyxy+C.xxzz;x12.xy-=i1;i=mod(i,289.0);',
    ' vec3 p=pm(pm(i.y+vec3(0.0,i1.y,1.0))+i.x+vec3(0.0,i1.x,1.0));',
    ' vec3 m=max(0.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.0);m=m*m;m=m*m;',
    ' vec3 x=2.0*fract(p*C.www)-1.0;vec3 h=abs(x)-0.5;vec3 ox=floor(x+0.5);vec3 a0=x-ox;',
    ' m*=1.79284291400159-0.85373472095314*(a0*a0+h*h);',
    ' vec3 g;g.x=a0.x*x0.x+h.x*x0.y;g.yz=a0.yz*x12.xz+h.yz*x12.yw;return 130.0*dot(m,g);}',
    'float fbm(vec2 p){return 0.62*sn(p)+0.26*sn(p*2.03+vec2(1.7,9.2))+0.12*sn(p*4.1+vec2(6.1,3.4));}',
    'void main(){',
    ' vec2 uv=gl_FragCoord.xy/uR;vec2 p=uv;p.x*=uR.x/uR.y;',
    ' float t=uT*0.04;',
    ' float w1=fbm(p*0.5+vec2(t,-t*0.6)+(uP-0.5)*0.25);',
    ' float w2=fbm(p*0.82+vec2(4.0-t*0.7,2.0+t)+w1*0.7);',
    ' float c=p.x*1.25+p.y*0.5+w1*1.15+w2*0.42;',
    ' float band=sin(c*3.6+t*1.3);',
    ' float sheen=pow(0.5+0.5*band,2.6);',
    ' float shade=pow(0.5-0.5*band,3.0);',
    ' vec3 col=mix(uA,uB,smoothstep(-0.5,0.6,w2));',
    ' col=mix(col,uC,smoothstep(-0.3,0.7,w1)*0.55);',
    ' col=mix(col,uD,sheen*0.6);',
    ' col*=1.0-shade*0.07;',
    ' float n=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453);',
    ' col+=(n-0.5)*0.012;',
    ' gl_FragColor=vec4(col,1.0);}'
  ].join('\n');

  function hex(h) { var n = parseInt(h.slice(1), 16); return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]; }

  function Silk(canvas, opts) {
    this.canvas = canvas;
    this.o = Object.assign({ colors: ['#f6ede4', '#ecd8cd', '#e7dccb', '#fffaf4'], res: 0.5, speed: 1 }, opts || {});
    this.ok = false; this.running = false; this.raf = 0; this.t = Math.random() * 40; this.last = 0;
    this.cur = this.o.colors.map(hex); this.from = this.cur; this.to = this.cur; this.mixT = 1;
    this.pointer = [0.5, 0.5]; this.pt = [0.5, 0.5];
    var gl = null;
    try { gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power', preserveDrawingBuffer: false }); } catch (e) { gl = null; }
    if (!gl) return;
    var sh = function (type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; };
    var vs = sh(gl.VERTEX_SHADER, VERT), fs = sh(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;
    var pr = gl.createProgram(); gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) return;
    gl.useProgram(pr);
    var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    this.gl = gl;
    this.u = { R: gl.getUniformLocation(pr, 'uR'), T: gl.getUniformLocation(pr, 'uT'), A: gl.getUniformLocation(pr, 'uA'), B: gl.getUniformLocation(pr, 'uB'), C: gl.getUniformLocation(pr, 'uC'), D: gl.getUniformLocation(pr, 'uD'), P: gl.getUniformLocation(pr, 'uP') };
    this.ok = true; this.sized = false;
    canvas.classList.add('is-live');
  }

  /* 幅と高さを渡されたときは画面を測り直さない */
  Silk.prototype.resize = function (cssW, cssH) {
    if (!this.ok) return;
    if (!(cssW > 0 && cssH > 0)) { var r = this.canvas.getBoundingClientRect(); cssW = r.width; cssH = r.height; }
    if (!(cssW > 0 && cssH > 0)) return;
    this.sized = true;
    var w = Math.max(2, Math.round(cssW * this.o.res)), h = Math.max(2, Math.round(cssH * this.o.res));
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
    this.gl.viewport(0, 0, w, h);
    if (!this.running) this.draw();
  };

  Silk.prototype.setColors = function (cols, ms) {
    this.from = this.cur; this.to = cols.map(hex);
    if (!ms) { this.cur = this.to; this.mixT = 1; if (!this.running) this.draw(); return; }
    this.mixT = 0; this.mixDur = ms / 1000;
    if (!this.running) this._kick();
  };

  Silk.prototype.setPointer = function (x, y) { this.pt = [x, y]; };

  Silk.prototype.draw = function () {
    if (!this.ok) return;
    if (!this.sized) { this.sized = true; this.resize(); return; }
    var gl = this.gl, u = this.u, c = this.cur;
    gl.uniform2f(u.R, this.canvas.width, this.canvas.height);
    gl.uniform1f(u.T, this.t);
    gl.uniform3f(u.A, c[0][0], c[0][1], c[0][2]); gl.uniform3f(u.B, c[1][0], c[1][1], c[1][2]);
    gl.uniform3f(u.C, c[2][0], c[2][1], c[2][2]); gl.uniform3f(u.D, c[3][0], c[3][1], c[3][2]);
    gl.uniform2f(u.P, this.pointer[0], this.pointer[1]);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  };

  Silk.prototype._kick = function () {
    var self = this;
    if (this.raf || !this.ok) return;
    this.last = 0;
    var step = function (now) {
      self.raf = 0;
      var dt = self.last ? Math.min(0.05, (now - self.last) / 1000) : 0.016; self.last = now;
      var busy = false;
      if (self.running) self.t += dt * self.o.speed;
      if (self.mixT < 1) {
        self.mixT = Math.min(1, self.mixT + dt / self.mixDur);
        var k = self.mixT * self.mixT * (3 - 2 * self.mixT);
        self.cur = self.from.map(function (a, i) { var b = self.to[i]; return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k]; });
        busy = true;
      }
      self.pointer[0] += (self.pt[0] - self.pointer[0]) * 0.04; self.pointer[1] += (self.pt[1] - self.pointer[1]) * 0.04;
      self.draw();
      if (self.running || busy) self.raf = global.requestAnimationFrame(step);
    };
    this.raf = global.requestAnimationFrame(step);
  };

  Silk.prototype.start = function () { if (this.running || !this.ok) return; this.running = true; this._kick(); };
  Silk.prototype.stop = function () { this.running = false; };
  Silk.prototype.finish = function () { if (!this.ok) return; this.mixT = 1; this.cur = this.to; this.draw(); };

  global.LumoiSilk = Silk;
})(window);
