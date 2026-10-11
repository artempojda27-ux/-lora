/* ÉLORA — фон «шовк і шкіра»: повільні теплі переливи + тонкі текучі лінії.
   Підключення: <div class="ambient"><i></i><i></i><i></i><canvas></canvas></div> і цей скрипт.
   Малює ~24 кадри/с, зупиняється у фоновій вкладці, при reduced-motion — один статичний кадр. */
(() => {
  const cv = document.querySelector('.ambient canvas');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
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
      ctx.strokeStyle = accent ? 'rgba(226,96,26,.16)' : 'rgba(59,42,30,.075)';
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
})();
