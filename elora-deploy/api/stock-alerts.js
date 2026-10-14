/* Нагадування про наявність у Telegram-групу. Викликає workflow оновлення каталогу одразу після коміту:
   порівнює каталог, що зараз на сайті (ще стара версія), з новою версією в репозиторії й надсилає,
   що закінчується в постачальників (4cases — 1–2 шт., взуття — останній розмір) і що зникло з наявності.
   Нічого не приймає ззовні: дані беруться лише з сайту й репозиторію; одна й та сама версія — одне повідомлення. */
const { chatId } = require('./_telegram');

const REPO = process.env.ELORA_REPO || 'artempojda27-ux/-lora';
const ROOT = process.env.ELORA_ROOT || 'elora-deploy';
const FILES = [['data/catalog.js', 'DATA', 'TAPULI'], ['data/4cases.js', 'DATA_4C', '4cases'], ['data/podium.js', 'DATA_PD', 'Podium']];
let lastSha = null;   // повтор для тієї ж версії не надсилаємо

const parse = (js, v) => { const m = js && js.match(new RegExp(`const ${v}=(\\[[\\s\\S]*?\\]);`)); return m ? JSON.parse(m[1]) : null; };
const low = p => (p.q != null && p.q > 0 && p.q <= 2) ? `залишилось ${p.q} шт.` : (p.sz && p.sz.length === 1 ? `останній розмір ${p.sz[0]}` : '');
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));

async function text(url, headers = {}) {
  const r = await fetch(url, {headers, cache: 'no-store'});
  return r.ok ? r.text() : null;
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  const token = process.env.TELEGRAM_BOT_TOKEN, chat = token && await chatId(req);
  if (!token || !chat) return res.status(503).json({ok: false, error: 'not_configured'});
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  const gh = {Accept: 'application/vnd.github.raw+json', 'User-Agent': 'elora-alerts',
    ...(process.env.GH_WRITE_TOKEN ? {Authorization: `Bearer ${process.env.GH_WRITE_TOKEN}`} : {})};

  const head = await fetch(`https://api.github.com/repos/${REPO}/commits/main`, {headers: {...gh, Accept: 'application/vnd.github+json'}});
  if (!head.ok) return res.status(502).json({ok: false, error: 'github'});
  const sha = (await head.json()).sha;
  if (sha === lastSha) return res.json({ok: true, skipped: 'same version'});

  const lowList = [], gone = [];
  for (const [file, v, name] of FILES) {
    const [oldJs, newJs] = await Promise.all([
      text(`https://${host}/${file}?v=${Date.now()}`),
      text(`https://api.github.com/repos/${REPO}/contents/${ROOT}/${file}?ref=${sha}`, gh)]);
    const before = parse(oldJs, v), after = parse(newJs, v);
    if (!before || !after) continue;
    const was = new Map(before.map(p => [String(p.id), p])), now = new Map(after.map(p => [String(p.id), p]));
    for (const [id, p] of now) {
      const o = was.get(id), l = low(p);
      if (l && (!o || low(o) !== l)) lowList.push({name, p, l});
    }
    for (const [id, p] of was) if (!now.has(id)) gone.push({name, p});
  }
  lastSha = sha;
  if (!lowList.length && !gone.length) return res.json({ok: true, changes: 0});

  const line = (x, extra) => `• ${esc(x.name)}: <a href="https://${host}/#p=${encodeURIComponent(x.p.id)}">${esc(x.p.t)}</a>${extra ? ` — ${esc(extra)}` : ''}`;
  const MAX = 25;
  const msg = [
    '📦 <b>Наявність у постачальників</b>',
    lowList.length ? `\n⚠️ <b>Закінчуються (${lowList.length})</b>` : null,
    ...lowList.slice(0, MAX).map(x => line(x, x.l)),
    lowList.length > MAX ? `…і ще ${lowList.length - MAX}` : null,
    gone.length ? `\n❌ <b>Зникли з наявності — прибрано з сайту (${gone.length})</b>` : null,
    ...gone.slice(0, MAX).map(x => `• ${esc(x.name)}: ${esc(x.p.t)}`),
    gone.length > MAX ? `…і ще ${gone.length - MAX}` : null,
  ].filter(Boolean).join('\n');
  const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chat_id: chat, text: msg, parse_mode: 'HTML', disable_web_page_preview: true, disable_notification: true})});
  return res.json({ok: r.ok, low: lowList.length, gone: gone.length});
};
