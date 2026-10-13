/* Перевірка наявності в постачальників у момент замовлення.
   check(items, host) -> Map(key -> true | false | null), key = `${id}|${size}`
     TAPULI  (id = group_id): свіжий XML-фід (лише наявне) — модель + розмір; кеш 5 хв
     4cases  (id = 4c-<slug>): сторінка товару, data-stock > 0
     Podium  (id = pd-<num>):  сторінка товару (посилання з data/podium.js), schema.org InStock
   null — не вдалося перевірити (таймаут, постачальник недоступний). */

const UA = {'User-Agent': 'Mozilla/5.0 (ELORA stock check)'};
const TAPULI = () => `https://tapuli.shop/price-xml/?datefrom=2020-01-01&dateto=${new Date().toISOString().slice(0, 10)}&xml-feed=1&platform=standard`;
const cache = {};   // живе між викликами, поки функція «тепла»

async function get(url, ms) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, {headers: UA, signal: ctl.signal});
    if (r.status === 404 || r.status === 410) return '';      // товар знято з продажу
    return r.ok ? await r.text() : null;
  } catch (e) {
    return null;
  } finally {
    clearTimeout(t);
  }
}

async function cached(key, ttl, load) {
  const c = cache[key];
  if (c && Date.now() - c.at < ttl) return c.v;
  const v = await load();
  if (v != null) cache[key] = {at: Date.now(), v};
  return v;
}

/* TAPULI: множина «group_id|розмір» з наявних пропозицій фіду */
const tapuliStock = () => cached('tapuli', 5 * 60e3, async () => {
  const xml = await get(TAPULI(), 15000);
  if (!xml || !xml.includes('<catalog')) return null;
  const set = new Set();
  for (const m of xml.matchAll(/<product\b[^>]*\bgroup_id="(\d+)"[^>]*>([\s\S]*?)<\/product>/g)) {
    if (/available="false"/.test(m[0].slice(0, 200))) continue;
    const size = (m[2].match(/<param name="Розмір">([^<]*)</) || [])[1];
    set.add(`${m[1]}|${size || ''}`);
  }
  return set;
});

/* посилання на сторінки Podium беремо з власного data/podium.js */
const podiumUrls = host => cached('pdurls', 30 * 60e3, async () => {
  const js = await get(`https://${host}/data/podium.js`, 4000);
  if (!js) return null;
  const m = js.match(/const DATA_PD=(\[[\s\S]*?\]);/);
  return m ? new Map(JSON.parse(m[1]).map(p => [p.id, p.u])) : null;
});

async function one(item, host) {
  const {id, size} = item;
  if (/^\d+$/.test(id)) {                                     // TAPULI
    const set = await tapuliStock();
    return set ? set.has(`${id}|${size === 'one size' ? '' : size}`) : null;
  }
  if (id.startsWith('4c-')) {                                 // 4cases
    const page = await get(`https://4cases.com.ua/products/${encodeURIComponent(id.slice(3))}`, 7000);
    if (page === null) return null;
    if (page === '') return false;
    const m = page.match(/data-stock="(\d*)"/);
    return m ? Number(m[1] || 0) > 0 : false;
  }
  if (id.startsWith('pd-')) {                                 // Podium
    const urls = await podiumUrls(host), url = urls && urls.get(id);
    if (!url) return null;
    const page = await get(url, 7000);
    if (page === null) return null;
    return /schema\.org\/InStock/.test(page);    // '' (404) -> false
  }
  return null;
}

async function check(items, host) {
  const out = new Map();
  await Promise.all(items.map(async i => out.set(`${i.id}|${i.size}`, await one(i, host).catch(() => null))));
  return out;
}

module.exports = {check};
