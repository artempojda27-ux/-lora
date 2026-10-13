/* Журнал замовлень: зашифровані (AES-256-GCM) файли orders/РРРР-ММ.enc у гілці `orders` репозиторію.
   Репозиторій публічний, тож у гілці лише шифротекст; ключ — тільки у Vercel.
   Змінні у Vercel: ORDERS_KEY (base64, 32 байти), GH_ORDERS_TOKEN (GitHub-токен із правом запису в репозиторій).
   Без них журнал просто вимкнений — замовлення все одно приходять у Telegram. */
const crypto = require('crypto');

const REPO = process.env.ELORA_REPO || 'artempojda27-ux/-lora';
const BRANCH = 'orders';
const enabled = () => !!(process.env.ORDERS_KEY && process.env.GH_ORDERS_TOKEN);
const key = () => Buffer.from(process.env.ORDERS_KEY, 'base64');

function enc(obj) {
  const iv = crypto.randomBytes(12), c = crypto.createCipheriv('aes-256-gcm', key(), iv);
  const data = Buffer.concat([c.update(JSON.stringify(obj), 'utf8'), c.final()]);
  return Buffer.concat([iv, c.getAuthTag(), data]).toString('base64');
}
function dec(b64) {
  const buf = Buffer.from(b64, 'base64'), d = crypto.createDecipheriv('aes-256-gcm', key(), buf.subarray(0, 12));
  d.setAuthTag(buf.subarray(12, 28));
  return JSON.parse(Buffer.concat([d.update(buf.subarray(28)), d.final()]).toString('utf8'));
}

const gh = (path, opt = {}) => fetch(`https://api.github.com/repos/${REPO}/${path}`, {...opt, headers: {
  Authorization: `Bearer ${process.env.GH_ORDERS_TOKEN}`, Accept: 'application/vnd.github+json',
  'Content-Type': 'application/json', 'User-Agent': 'elora-orders', ...(opt.headers || {})}});

/* гілка orders створюється при першому замовленні (від main; деплой цієї гілки вимкнено у vercel.json) */
async function ensureBranch() {
  if ((await gh(`git/ref/heads/${BRANCH}`)).ok) return;
  const main = await (await gh('git/ref/heads/main')).json();
  await gh('git/refs', {method: 'POST', body: JSON.stringify({ref: `refs/heads/${BRANCH}`, sha: main.object.sha})});
}

const monthOf = d => new Date(d).toISOString().slice(0, 7);
const pathOf = m => `orders/${m}.enc`;

async function readMonth(m) {
  const r = await gh(`contents/${pathOf(m)}?ref=${BRANCH}`);
  if (r.status === 404) return {sha: null, list: []};
  if (!r.ok) throw new Error(`github ${r.status}`);
  const j = await r.json();
  const raw = Buffer.from(j.content, 'base64').toString('utf8').trim();
  return {sha: j.sha, list: raw ? dec(raw) : []};
}

async function writeMonth(m, list, sha, msg) {
  return gh(`contents/${pathOf(m)}`, {method: 'PUT', body: JSON.stringify({
    message: msg, branch: BRANCH, content: Buffer.from(enc(list) + '\n').toString('base64'), ...(sha ? {sha} : {})})});
}

/* зміна з повтором на випадок одночасного запису (409/422 — файл щойно змінився) */
async function mutate(m, fn, msg) {
  for (let i = 0; i < 4; i++) {
    const {sha, list} = await readMonth(m);
    const out = fn(list);
    if (out === null) return null;
    const r = await writeMonth(m, out.list, sha, msg);
    if (r.ok) return out.value;
    if (r.status !== 409 && r.status !== 422) throw new Error(`github ${r.status}`);
    await new Promise(res => setTimeout(res, 300 * (i + 1)));
  }
  throw new Error('github conflict');
}

async function add(order) {
  if (!enabled()) return false;
  await ensureBranch();
  return mutate(monthOf(order.at), list => ({list: [...list, order], value: true}), `order ${order.id}`);
}

/* останні місяці (за замовчуванням 3) */
async function list(months = 3) {
  if (!enabled()) return null;
  const out = [], now = new Date();
  for (let i = 0; i < months; i++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1));
    out.push(...(await readMonth(monthOf(d))).list);
  }
  return out.sort((a, b) => (a.at < b.at ? 1 : -1));
}

async function update(id, at, patch) {
  if (!enabled()) return null;
  return mutate(monthOf(at), lst => {
    const i = lst.findIndex(o => o.id === id);
    if (i < 0) return null;
    const o = {...lst[i], ...patch, history: [...(lst[i].history || []), {at: new Date().toISOString(), ...patch}]};
    const copy = lst.slice(); copy[i] = o;
    return {list: copy, value: o};
  }, `order ${id}: ${patch.status || 'update'}`);
}

/* самодіагностика для адмінки: що відповідає GitHub */
async function diag() {
  const out = {enabled: enabled()};
  if (!out.enabled) return out;
  const ref = await gh(`git/ref/heads/${BRANCH}`); out.ref = ref.status;
  if (ref.status === 404) {
    const main = await gh('git/ref/heads/main'); out.main = main.status;
    if (main.ok) {
      const sha = (await main.json()).object.sha;
      const c = await gh('git/refs', {method: 'POST', body: JSON.stringify({ref: `refs/heads/${BRANCH}`, sha})});
      out.create = c.status; if (!c.ok) out.createError = (await c.text()).slice(0, 300);
    }
  }
  return out;
}

module.exports = {enabled, add, list, update, diag};
