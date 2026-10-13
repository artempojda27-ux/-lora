/* Каталог вітрини для серверних функцій: id товару -> {s: постачальник, u: сторінка в постачальника}.
   Читає власні data/*.js з сайту (кеш 30 хв) і config/suppliers.json (контакти постачальників). */

const cache = {};

async function load(url, ms = 6000) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, {signal: ctl.signal});
    return r.ok ? await r.text() : null;
  } catch (e) {
    return null;
  } finally {
    clearTimeout(t);
  }
}

async function cached(key, ttl, fn) {
  const c = cache[key];
  if (c && Date.now() - c.at < ttl) return c.v;
  const v = await fn();
  if (v) cache[key] = {at: Date.now(), v};
  return v;
}

const SOURCES = [['data/catalog.js', 'DATA', 'tapuli'], ['data/4cases.js', 'DATA_4C', '4cases'], ['data/podium.js', 'DATA_PD', 'podium']];

/* id -> {s, u, t} */
const products = host => cached('products', 30 * 60e3, async () => {
  const map = new Map();
  await Promise.all(SOURCES.map(async ([file, v, s]) => {
    const js = await load(`https://${host}/${file}`);
    const m = js && js.match(new RegExp(`const ${v}=(\\[[\\s\\S]*?\\]);`));
    if (!m) return;
    for (const p of JSON.parse(m[1])) {
      const u = p.u || (s === '4cases' ? `https://4cases.com.ua/products/${p.id.slice(3)}` : null);
      map.set(String(p.id), {s, u, t: p.t});
    }
  }));
  return map.size ? map : null;
});

const suppliers = host => cached('suppliers', 10 * 60e3, async () => {
  const j = await load(`https://${host}/config/suppliers.json`);
  try { return j ? JSON.parse(j) : null; } catch (e) { return null; }
});

/* постачальник за форматом id, якщо каталог недоступний */
const supplierOf = id => /^\d+$/.test(id) ? 'tapuli' : id.startsWith('4c-') ? '4cases' : id.startsWith('pd-') ? 'podium' : null;

module.exports = {products, suppliers, supplierOf};
