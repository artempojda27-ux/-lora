/* ÉLORA — як рахується ціна на сайті (спільне для вітрини й адмінки).
   data/prices.js задає:
     RULES  = {tapuli|4cases|podium: {k: множник, a: надбавка ₴, end: '99' | '79' | '0'}} — наценка постачальника;
     PRICES = {id: {p, o}} — своя ціна окремого товару, перекриває наценку.
   Наценка рахується завжди від ціни постачальника, тож її неможливо застосувати двічі,
   а нові товари з автооновлення каталогу отримують її самі. */
(function(){
  const rules = () => typeof RULES !== 'undefined' && RULES ? RULES : {};
  const manual = () => typeof PRICES !== 'undefined' && PRICES ? PRICES : {};

  /* закінчення ціни: найближче …99 / …79, або до 10 ₴ */
  function end(v, mode){
    if(!isFinite(v)) return v;
    v = Math.max(0, v);
    if(mode === '99') return Math.max(99, Math.round((v + 1) / 100) * 100 - 1);
    if(mode === '79') return Math.max(79, Math.round((v - 79) / 100) * 100 + 79);
    return Math.round(v / 10) * 10;
  }
  function byRule(v, r){
    if(v == null || !r) return v;
    return end(v * (Number(r.k) || 1) + (Number(r.a) || 0), r.end);
  }
  /* ціна товару на сайті: {p, o, how: 'own' | 'rule' | 'feed'} */
  function price(id, s, p0, o0, R, M){
    R = R || rules(); M = M || manual();
    const m = M[id];
    if(m && m.p != null) return {p: m.p, o: 'o' in m ? m.o : null, how: 'own'};
    const r = R[s];
    if(!r) return {p: p0, o: o0 ?? null, how: 'feed'};
    const p = byRule(p0, r), o = o0 ? byRule(o0, r) : null;
    return {p, o: o && o > p ? o : null, how: 'rule'};
  }
  window.ELORA_PRICE = {end, byRule, price};
})();
