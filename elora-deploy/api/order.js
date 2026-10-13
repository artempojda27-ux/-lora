/* ÉLORA — приймання замовлень: POST /api/order -> повідомлення в Telegram.
   Змінна оточення у Vercel (Settings → Environment Variables):
     TELEGRAM_BOT_TOKEN — токен бота від @BotFather
   Чат для замовлень: TELEGRAM_CHAT_ID або config/telegram.json, який зберігає адмінка (кнопка «Telegram»).
   Без токена чи чату функція відповідає 503, і вітрина просить покупця зателефонувати. */

const { chatId } = require('./_telegram');
const { check } = require('./_stock');
const MARK = {true: '✅', false: '❌ немає', null: '⚠️ не перевірено'};

const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
const str = (v, max) => typeof v === 'string' ? v.trim().slice(0, max) : '';
const money = n => Math.round(n).toLocaleString('uk-UA').replace(/ /g, ' ') + ' ₴';

/* мессенджер покупця -> клікабельне посилання в повідомленні */
function messenger(via, handle) {
  const h = handle.trim(), user = h.replace(/^@/, '').replace(/^https?:\/\/[^/]+\//, '').replace(/\/.*$/, '');
  const num = h.replace(/\D/g, ''), phone = num.length === 10 ? '38' + num : num;
  if (via === 'instagram') return `Instagram: <a href="https://instagram.com/${encodeURIComponent(user)}">@${esc(user)}</a>`;
  if (via === 'whatsapp') return `WhatsApp: <a href="https://wa.me/${phone}">${esc(h)}</a>`;
  return /^[+\d\s()-]+$/.test(h) && num.length >= 10
    ? `Telegram: <a href="https://t.me/+${phone}">${esc(h)}</a>`
    : `Telegram: <a href="https://t.me/${encodeURIComponent(user)}">@${esc(user)}</a>`;
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ok: false, error: 'method'});
  }
  const token = process.env.TELEGRAM_BOT_TOKEN, chat = token && await chatId(req);
  if (!token || !chat) return res.status(503).json({ok: false, error: 'not_configured'});

  let b = req.body;
  if (typeof b === 'string') { try { b = JSON.parse(b); } catch { b = null; } }
  if (!b || typeof b !== 'object') return res.status(400).json({ok: false, error: 'body'});
  if (b.company) return res.status(200).json({ok: true, id: '—'});   // пастка для ботів

  const c = {name: str(b.name, 80), phone: str(b.phone, 30), city: str(b.city, 80),
             dep: str(b.dep, 120), note: str(b.note, 500)};
  const digits = c.phone.replace(/\D/g, '');
  if (c.name.length < 2 || digits.length < 10 || digits.length > 13 || !c.city || !c.dep)
    return res.status(400).json({ok: false, error: 'contacts'});
  const via = ['telegram', 'whatsapp', 'instagram'].includes(b.contact && b.contact.via) ? b.contact.via : '';
  const handle = str(b.contact && b.contact.handle, 60);
  if (!via || handle.replace(/[@\s]/g, '').length < 3) return res.status(400).json({ok: false, error: 'contacts'});

  const items = (Array.isArray(b.items) ? b.items : []).slice(0, 30).map(i => ({
    id: str(i && i.id, 80), t: str(i && i.t, 160), col: str(i && i.col, 40),
    size: str(i && i.size, 12), price: Number(i && i.price) || 0,
  })).filter(i => i.id && i.t);
  if (!items.length) return res.status(400).json({ok: false, error: 'items'});

  const id = Date.now().toString(36).slice(-5).toUpperCase();
  /* наявність у постачальників на момент замовлення */
  const stock = await check(items, req.headers['x-forwarded-host'] || req.headers.host).catch(() => new Map());
  const st = i => MARK[String(stock.has(`${i.id}|${i.size}`) ? stock.get(`${i.id}|${i.size}`) : null)];
  const total = items.reduce((s, i) => s + i.price, 0);
  const text = [
    `<b>Нове замовлення №${id}</b>`,
    '',
    ...items.map((i, n) => `${n + 1}. ${st(i)} ${esc(i.t)}${i.col ? ` · ${esc(i.col)}` : ''}` +
      `${i.size && i.size !== 'one size' ? ` · розмір <b>${esc(i.size)}</b>` : ''} — ${money(i.price)}` +
      `\n    <code>${esc(i.id)}</code>`),
    '',
    `<b>Разом: ${money(total)}</b>`,
    '',
    `👤 ${esc(c.name)}`,
    `📞 <a href="tel:+${digits.length === 10 ? '38' + digits : digits}">${esc(c.phone)}</a>`,
    `📦 ${esc(c.city)}, ${esc(c.dep)}`,
    `💬 ${messenger(via, handle)}`,
    c.note ? `📝 ${esc(c.note)}` : null,
  ].filter(l => l !== null).join('\n');

  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({chat_id: chat, text, parse_mode: 'HTML', disable_web_page_preview: true}),
    });
    if (!r.ok) throw new Error(`telegram ${r.status}`);
    return res.status(200).json({ok: true, id});
  } catch (e) {
    console.error('order', e);
    return res.status(502).json({ok: false, error: 'send'});
  }
};
