/* Журнал замовлень для адмінки (/admin → «Замовлення»). Доступ — GitHub-токен адміна.
   GET  /api/orders                         -> {ok, enabled, orders:[…]}
   POST /api/orders {id, at, status, ttn, comment} -> {ok, order}
   Зміну статусу бот дублює в групу відповіддю на початкове замовлення. */
const { isAdmin, chatId } = require('./_telegram');
const journal = require('./_orders');

const STATUS = {new: '🆕 Нове', confirmed: '☑️ Підтверджено з клієнтом', supplier: '📨 Передано постачальнику',
  shipped: '🚚 Відправлено', done: '✅ Виконано', cancelled: '✖️ Скасовано'};

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!(await isAdmin(req))) return res.status(401).json({ok: false, error: 'auth'});
  if (!journal.enabled()) return res.json({ok: true, enabled: false, orders: []});

  if (req.method === 'GET') {
    try { return res.json({ok: true, enabled: true, statuses: STATUS, orders: await journal.list(3)}); }
    catch (e) { console.error(e); return res.status(502).json({ok: false, error: 'storage'}); }
  }
  if (req.method !== 'POST') return res.status(405).json({ok: false});

  let b = req.body;
  if (typeof b === 'string') { try { b = JSON.parse(b); } catch { b = {}; } }
  if (!b || !b.id || !b.at) return res.status(400).json({ok: false, error: 'id'});
  const patch = {};
  if (b.status && STATUS[b.status]) patch.status = b.status;
  if (typeof b.ttn === 'string') patch.ttn = b.ttn.replace(/\D/g, '').slice(0, 20) || null;
  if (typeof b.comment === 'string') patch.comment = b.comment.slice(0, 500);
  const order = await journal.update(String(b.id), String(b.at), patch).catch(e => { console.error(e); return undefined; });
  if (order === undefined) return res.status(502).json({ok: false, error: 'storage'});
  if (order === null) return res.status(404).json({ok: false, error: 'not_found'});

  /* коротке оновлення в Telegram-групу, відповіддю на замовлення */
  const token = process.env.TELEGRAM_BOT_TOKEN, chat = token && await chatId(req);
  if (chat && (patch.status || patch.ttn)) {
    const text = [`№${order.id}: ${STATUS[order.status] || order.status}`,
      order.ttn ? `ТТН <code>${order.ttn}</code> · <a href="https://novaposhta.ua/tracking/?cargo_number=${order.ttn}">відстежити</a>` : null,
      patch.comment ? `📝 ${patch.comment.replace(/[<>&]/g, '')}` : null].filter(Boolean).join('\n');
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({chat_id: chat, text, parse_mode: 'HTML', disable_web_page_preview: true,
        ...(order.tg ? {reply_parameters: {message_id: order.tg, allow_sending_without_reply: true}} : {})})}).catch(() => {});
  }
  return res.json({ok: true, order});
};
