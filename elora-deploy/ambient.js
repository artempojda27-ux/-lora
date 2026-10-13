/* ÉLORA — фон «шовк»: WebGL-шейдер атласних складок перлинно-сірого кольору з холодними відблисками.
   Підключення: <div class="ambient"><i></i><i></i><i></i><canvas></canvas></div> і цей скрипт.
   Малюється в зниженій роздільності (тканина гладка), ~30 кадрів/с, пауза у фоновій вкладці,
   при reduced-motion — один статичний кадр. Без WebGL — запасний фон: теплі переливи й тонкі лінії. */
(() => {
  const cv = document.querySelector('.ambient canvas');
  if (!cv) return;
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const gl = cv.getContext('webgl', {antialias: false, depth: false, powerPreference: 'low-power'});
  if (gl && silk(gl)) return;
  lines(cv.getContext('2d'));

  function silk(g) {
    const FS = `
precision mediump float;
uniform vec2 r; uniform float t;
float silk(vec2 p){
  float w=1.7*sin(p.y*.55+t*.11)+1.1*sin(p.x*.32-p.y*.21+t*.07)+.6*sin(p.x*.9+p.y*.4-t*.05);
  float a=dot(p,vec2(.88,.47));
  return sin(a*1.1+w)+.42*sin(a*2.2+w*1.35+1.1)+.15*sin(a*4.1+w*.6);
}
void main(){
  vec2 uv=gl_FragCoord.xy/r.y; vec2 p=uv*4.6;
  float e=.008, hgt=silk(p);
  vec3 N=normalize(vec3(-(silk(p+vec2(e,0.))-hgt)/e*.40,-(silk(p+vec2(0.,e))-hgt)/e*.40,1.));
  vec3 L=normalize(vec3(-.5,.6,.62));
  float diff=clamp(dot(N,L),0.,1.);
  vec3 H=normalize(L+vec3(0.,0.,1.));
  float nh=clamp(dot(N,H),0.,1.);
  float spec=pow(nh,90.)*.42+pow(nh,16.)*.07;
  vec3 shade=vec3(.70,.72,.75), mid=vec3(.86,.87,.885), light=vec3(.955,.96,.968);
  vec3 col=mix(shade,mid,smoothstep(.05,.6,diff));
  col=mix(col,light,smoothstep(.55,1.,diff));
  col+=spec*vec3(.96,.98,1.);
  vec3 over=max(col-vec3(.955),0.);
  col=min(col,vec3(.955))+vec3(.04,.035,.028)*(1.-exp(-over*14.));
  float x=uv.x/(r.x/r.y);
  col=mix(col,col*vec3(.96,.99,1.04),.3*smoothstep(.4,1.,x)*(1.-uv.y));
  col=mix(col,vec3(.905,.91,.915),.16);
  gl_FragColor=vec4(col,1.);
}`;
    const mk = (type, src) => { const s = g.createShader(type); g.shaderSource(s, src); g.compileShader(s);
      return g.getShaderParameter(s, g.COMPILE_STATUS) ? s : null; };
    const vs = mk(g.VERTEX_SHADER, 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}'), fs = mk(g.FRAGMENT_SHADER, FS);
    if (!vs || !fs) return false;
    const pr = g.createProgram(); g.attachShader(pr, vs); g.attachShader(pr, fs); g.linkProgram(pr);
    if (!g.getProgramParameter(pr, g.LINK_STATUS)) return false;
    g.useProgram(pr);
    g.bindBuffer(g.ARRAY_BUFFER, g.createBuffer());
    g.bufferData(g.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), g.STATIC_DRAW);
    const a = g.getAttribLocation(pr, 'a'); g.enableVertexAttribArray(a); g.vertexAttribPointer(a, 2, g.FLOAT, false, 0, 0);
    const uR = g.getUniformLocation(pr, 'r'), uT = g.getUniformLocation(pr, 't');
    document.querySelector('.ambient').classList.add('silk');
    const SCALE = .4;                       // тканина гладка — вистачає 40% роздільності
    let t = 12 + Math.random() * 40, last = 0, raf;
    const size = () => { cv.width = Math.ceil(innerWidth * SCALE); cv.height = Math.ceil(innerHeight * SCALE);
      g.viewport(0, 0, cv.width, cv.height); g.uniform2f(uR, cv.width, cv.height); draw(); };
    const draw = () => { g.uniform1f(uT, t); g.drawArrays(g.TRIANGLES, 0, 3); };
    const loop = now => { raf = requestAnimationFrame(loop); if (now - last < 33) return;
      t += Math.min(now - last, 100) / 1000; last = now; draw(); };
    size(); addEventListener('resize', size);
    if (still) return true;
    document.addEventListener('visibilitychange', () => { cancelAnimationFrame(raf);
      if (!document.hidden) { last = performance.now(); raf = requestAnimationFrame(loop); } });
    raf = requestAnimationFrame(loop);
    return true;
  }

  function lines(ctx) {
  let w, h, dpr, lines, t = Math.random() * 1000, last = 0, raf;

  function size() {
    dpr = Math.min(devicePixelRatio || 1, 1.5);
    w = innerWidth; h = innerHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    lines = w < 700 ? 14 : 22;
    if (still) frame();
  }

  function frame() {
    ctx.clearRect(0, 0, w, h);
    const step = w < 700 ? 14 : 10;
    for (let k = 0; k < lines; k++) {
      const base = h * (k + .5) / lines;
      const accent = k % 6 === 3;
      ctx.beginPath();
      for (let x = -20; x <= w + 20; x += step) {
        const y = base
          + Math.sin(x * .0021 + t * .11 + k * .37) * 46
          + Math.sin(x * .0047 - t * .07 + k * .19) * 18
          + Math.sin(x * .0009 + t * .04) * 70;
        x < -10 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.strokeStyle = accent ? 'rgba(80,96,118,.16)' : 'rgba(20,24,30,.07)';
      ctx.lineWidth = accent ? 1.1 : .8;
      ctx.stroke();
    }
  }

  function loop(now) {
    raf = requestAnimationFrame(loop);
    if (now - last < 42) return;
    t += Math.min(now - last, 100) / 1000;
    last = now;
    frame();
  }

  size();
  addEventListener('resize', size);
  if (still) return;
  document.addEventListener('visibilitychange', () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) { last = performance.now(); raf = requestAnimationFrame(loop); }
  });
  raf = requestAnimationFrame(loop);
  }
})();
