/* ÉLORA — налаштування Telegram з адмінки (/admin → «Telegram»).
   GET  /api/tg?action=status — чи є токен бота у Vercel, ім'я бота, поточний чат
   GET  /api/tg?action=chats  — чати, що нещодавно писали боту (щоб обрати, куди слати замовлення)
   POST /api/tg {action:'test', chat_id} — тестове повідомлення
   Доступ — лише з GitHub-токеном адміна (право запису в репозиторій). */
const { chatId, isAdmin } = require('./_telegram');

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!(await isAdmin(req))) return res.status(401).json({ok: false, error: 'auth'});
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const api = (m, body) => fetch(`https://api.telegram.org/bot${token}/${m}`, body ? {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : undefined)
    .then(r => r.json());
  const q = req.method === 'POST' ? (typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {}) : req.query;

  if (q.action === 'status') {
    if (!token) return res.json({ok: true, token: false});
    const me = await api('getMe');
    return res.json({ok: true, token: !!me.ok, bot: me.ok ? me.result.username : null, chat: await chatId(req)});
  }
  if (!token) return res.status(503).json({ok: false, error: 'no_token'});

  if (q.action === 'chats') {
    const u = await api('getUpdates');
    if (!u.ok) return res.status(502).json({ok: false, error: u.description || 'telegram'});
    const chats = new Map();
    for (const up of u.result || []) {
      const m = up.message || up.channel_post || up.my_chat_member || {};
      const c = m.chat; if (!c) continue;
      chats.set(String(c.id), {id: String(c.id), type: c.type,
        title: c.title || [c.first_name, c.last_name].filter(Boolean).join(' ') || c.username || String(c.id),
        username: c.username || null});
    }
    return res.json({ok: true, chats: [...chats.values()].reverse()});
  }
  if (q.action === 'test') {
    const chat = String(q.chat_id || await chatId(req) || '');
    if (!chat) return res.status(400).json({ok: false, error: 'no_chat'});
    const r = await api('sendMessage', {chat_id: chat, parse_mode: 'HTML',
      text: '✅ <b>ÉLORA</b>: бот підключено. Сюди приходитимуть замовлення з сайту.'});
    return r.ok ? res.json({ok: true}) : res.status(502).json({ok: false, error: r.description || 'telegram'});
  }
  return res.status(400).json({ok: false, error: 'action'});
};
