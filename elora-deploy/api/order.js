/* ÉLORA — приймання замовлень: POST /api/order -> повідомлення в Telegram.
   Змінні оточення у Vercel (Settings → Environment Variables):
     TELEGRAM_BOT_TOKEN — токен бота від @BotFather
     TELEGRAM_CHAT_ID   — id чату/групи, куди слати замовлення
   Без них функція відповідає 503, і вітрина просить покупця зателефонувати. */

const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
const str = (v, max) => typeof v === 'string' ? v.trim().slice(0, max) : '';
const money = n => Math.round(n).toLocaleString('uk-UA').replace(/ /g, ' ') + ' ₴';

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ok: false, error: 'method'});
  }
  const token = process.env.TELEGRAM_BOT_TOKEN, chat = process.env.TELEGRAM_CHAT_ID;
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

  const items = (Array.isArray(b.items) ? b.items : []).slice(0, 30).map(i => ({
    id: str(i && i.id, 80), t: str(i && i.t, 160), col: str(i && i.col, 40),
    size: str(i && i.size, 12), price: Number(i && i.price) || 0,
  })).filter(i => i.id && i.t);
  if (!items.length) return res.status(400).json({ok: false, error: 'items'});

  const id = Date.now().toString(36).slice(-5).toUpperCase();
  const total = items.reduce((s, i) => s + i.price, 0);
  const text = [
    `<b>Нове замовлення №${id}</b>`,
    '',
    ...items.map((i, n) => `${n + 1}. ${esc(i.t)}${i.col ? ` · ${esc(i.col)}` : ''}` +
      `${i.size && i.size !== 'one size' ? ` · розмір <b>${esc(i.size)}</b>` : ''} — ${money(i.price)}` +
      `\n    <code>${esc(i.id)}</code>`),
    '',
    `<b>Разом: ${money(total)}</b>`,
    '',
    `👤 ${esc(c.name)}`,
    `📞 <a href="tel:+${digits.length === 10 ? '38' + digits : digits}">${esc(c.phone)}</a>`,
    `📦 ${esc(c.city)}, ${esc(c.dep)}`,
    c.note ? `💬 ${esc(c.note)}` : null,
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
