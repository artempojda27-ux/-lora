/* ÉLORA — приймання замовлень: POST /api/order -> повідомлення в Telegram.
   Змінна оточення у Vercel (Settings → Environment Variables):
     TELEGRAM_BOT_TOKEN — токен бота від @BotFather
   Чат для замовлень: TELEGRAM_CHAT_ID або config/telegram.json, який зберігає адмінка (кнопка «Telegram»).
   Без токена чи чату функція відповідає 503, і вітрина просить покупця зателефонувати. */

const { chatId } = require('./_telegram');
const { check } = require('./_stock');
const { products, suppliers, supplierOf } = require('./_catalog');
const journal = require('./_orders');
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
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  /* наявність у постачальників, каталог (посилання) і контакти постачальників — паралельно */
  const [stock, cat, sup] = await Promise.all([
    check(items, host).catch(() => new Map()), products(host).catch(() => null), suppliers(host).catch(() => null)]);
  const st = i => MARK[String(stock.has(`${i.id}|${i.size}`) ? stock.get(`${i.id}|${i.size}`) : null)];
  const info = i => (cat && cat.get(i.id)) || {s: supplierOf(i.id), u: null};
  const sizeTxt = i => i.size && i.size !== 'one size' ? `розмір ${i.size}` : '';
  const total = items.reduce((s, i) => s + i.price, 0);
  const tel = `+${digits.length === 10 ? '38' + digits : digits}`;

  /* 1) замовлення для менеджера: товар — посилання на картку на вітрині, поруч — у постачальника */
  const text = [
    `<b>Нове замовлення №${id}</b>`,
    '',
    ...items.map((i, n) => {
      const x = info(i), sp = sup && sup[x.s];
      return `${n + 1}. ${st(i)} <a href="https://${host}/#p=${encodeURIComponent(i.id)}">${esc(i.t)}</a>` +
        `${i.col ? ` · ${esc(i.col)}` : ''}${sizeTxt(i) ? ` · <b>${esc(sizeTxt(i))}</b>` : ''} — ${money(i.price)}` +
        `\n    ↳ ${x.u ? `<a href="${esc(x.u)}">${esc(sp ? sp.name : x.s || 'постачальник')}</a>` : esc(sp ? sp.name : x.s || '—')}` +
        ` · арт. <code>${esc(i.id.replace(/^(4c|pd)-/, ''))}</code>`;
    }),
    '',
    `<b>Разом: ${money(total)}</b>`,
    '',
    `👤 ${esc(c.name)}`,
    `📞 <a href="tel:${tel}">${esc(c.phone)}</a>`,
    `📦 ${esc(c.city)}, ${esc(c.dep)}`,
    `💬 ${messenger(via, handle)}`,
    c.note ? `📝 ${esc(c.note)}` : null,
  ].filter(l => l !== null).join('\n');

  /* під замовленням — по дві кнопки на кожен товар: картка на нашому сайті і той самий товар у постачальника */
  const keyboard = items.map((i, n) => {
    const x = info(i), sp = sup && sup[x.s], label = items.length > 1 ? `${n + 1}. ` : '';
    return [
      {text: `🛍 ${label}Наш сайт`, url: `https://${host}/#p=${encodeURIComponent(i.id)}`},
      x.u && {text: `📦 ${label}${sp ? sp.name : x.s || 'Постачальник'}`, url: x.u},
    ].filter(Boolean);
  });

  /* 2) заявки постачальникам: по одній на кожного — текст копіюється дотиком або пересилається */
  const groups = new Map();
  items.forEach(i => { const s = info(i).s || 'other'; groups.set(s, [...(groups.get(s) || []), i]); });
  const orders = [...groups].map(([s, list]) => {
    const sp = (sup && sup[s]) || {name: s};
    const sum = list.reduce((a, i) => a + i.price, 0);
    const body = [
      `Дропшипінг, замовлення ${id}`,
      ...list.map((i, n) => `${n + 1}) арт. ${i.id.replace(/^(4c|pd)-/, '')} — ${i.t}` +
        `${i.col ? `, ${i.col}` : ''}${sizeTxt(i) ? `, ${sizeTxt(i)}` : ''} — 1 шт.`),
      `Отримувач: ${c.name}`,
      `Телефон: ${c.phone}`,
      `Нова пошта: ${c.city}, ${c.dep}`,
      `Накладений платіж: ${money(sum)}`,
    ].join('\n');
    const buttons = [
      sp.telegram && {text: `✉️ Написати ${sp.name}`, url: sp.telegram},
      sp.instagram && {text: 'Instagram', url: sp.instagram},
      ...list.map(i => info(i).u).filter(Boolean).slice(0, 3).map((u, n) => ({text: `🔗 Товар ${list.length > 1 ? n + 1 : ''}`.trim(), url: u})),
    ].filter(Boolean);
    return {
      text: [`📦 <b>Заявка для ${esc(sp.name)}</b> · №${id}`,
        [sp.phone && `📞 ${esc(sp.phone)}`, sp.email && `✉️ ${esc(sp.email)}`].filter(Boolean).join(' · ') || null,
        '', `<pre>${esc(body)}</pre>`].filter(l => l !== null).join('\n'),
      reply_markup: buttons.length ? {inline_keyboard: [buttons.slice(0, 2), buttons.slice(2)].filter(r => r.length)} : undefined,
    };
  });

  const send = m => fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chat_id: chat, parse_mode: 'HTML', disable_web_page_preview: true, ...m}),
  });
  try {
    const r = await send({text, reply_markup: {inline_keyboard: keyboard}});
    if (!r.ok) throw new Error(`telegram ${r.status}`);
    const msg = await r.json().catch(() => ({}));
    for (const m of orders) await send(m).catch(e => console.error('supplier msg', e));
    /* журнал замовлень в адмінці (зашифровано); помилка журналу не ламає замовлення */
    await journal.add({
      id, at: new Date().toISOString(), status: 'new', total,
      tg: msg.result ? msg.result.message_id : null,
      customer: {...c, via, handle},
      items: items.map(i => ({...i, s: info(i).s, u: info(i).u,
        stock: stock.has(`${i.id}|${i.size}`) ? stock.get(`${i.id}|${i.size}`) : null})),
    }).catch(e => console.error('journal', e));
    return res.status(200).json({ok: true, id});
  } catch (e) {
    console.error('order', e);
    return res.status(502).json({ok: false, error: 'send'});
  }
};
