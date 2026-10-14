/* Дії адмінки без GitHub-токена в браузері (доступ — секретний ключ із посилання, X-Admin-Key):
   POST /api/admin {action:'prices', prices:{id:{p,o}}}  -> data/prices.js
   POST /api/admin {action:'sync'}                       -> запуск оновлення каталогу (GitHub Actions)
   POST /api/admin {action:'telegram', chat_id}          -> config/telegram.json
   GET  /api/admin                                       -> {ok, write} (чи налаштований запис) */
const { isAdmin } = require('./_telegram');
const { putFile, dispatch, enabled } = require('./_gh');

const ROOT = process.env.ELORA_ROOT || 'elora-deploy';

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!(await isAdmin(req))) return res.status(401).json({ok: false, error: 'auth'});
  if (req.method === 'GET') return res.json({ok: true, write: enabled()});
  if (req.method !== 'POST') return res.status(405).json({ok: false});
  if (!enabled()) return res.status(503).json({ok: false, error: 'no_write_token'});
  let b = req.body;
  if (typeof b === 'string') { try { b = JSON.parse(b); } catch { b = {}; } }
  b = b || {};

  if (b.action === 'prices') {
    const src = b.prices && typeof b.prices === 'object' ? b.prices : null;
    if (!src) return res.status(400).json({ok: false, error: 'prices'});
    const out = {};
    for (const [id, v] of Object.entries(src).slice(0, 5000)) {
      const p = Number(v && v.p), o = v && v.o != null ? Number(v.o) : null;
      if (!/^[\w-]{1,80}$/.test(id) || !(p >= 0) || (o !== null && !(o >= 0))) continue;
      out[id] = {p, o};
    }
    const text = '/* ÉLORA — ручні ціни з admin.html. Перекривають ціни фідів: {id: {p: ціна, o: стара ціна | null}} */\n' +
      'const PRICES=' + JSON.stringify(out) + ';\n';
    const n = Object.keys(out).length;
    const r = await putFile(`${ROOT}/data/prices.js`, text, `Ціни: ${n} ручних позицій (admin.html)`);
    return r.ok ? res.json({ok: true, saved: n}) : res.status(502).json({ok: false, error: 'github', ...r});
  }
  if (b.action === 'sync') {
    const r = await dispatch('catalog.yml');
    return r.ok ? res.json({ok: true}) : res.status(502).json({ok: false, error: 'github', status: r.status});
  }
  if (b.action === 'telegram') {
    const chat = String(b.chat_id || '');
    if (!/^-?\d{3,20}$/.test(chat)) return res.status(400).json({ok: false, error: 'chat'});
    const r = await putFile(`${ROOT}/config/telegram.json`, JSON.stringify({chat_id: chat}) + '\n', 'Telegram: чат для замовлень (admin.html)');
    return r.ok ? res.json({ok: true}) : res.status(502).json({ok: false, error: 'github', ...r});
  }
  if (b.action === 'test-write') {   // самоперевірка запису: чи має токен право писати
    const r = await putFile(`${ROOT}/config/.admin-check`, new Date().toISOString() + '\n', 'admin: перевірка запису');
    return res.json({ok: r.ok, ...r});
  }
  return res.status(400).json({ok: false, error: 'action'});
};
