/* POST /api/stock {items:[{id, size}]} -> {ok, stock: {"id|size": true|false|null}}
   Вітрина викликає перед оформленням замовлення, щоб попередити про розпродане. */
const { check } = require('./_stock');

module.exports = async (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ok: false});
  let b = req.body;
  if (typeof b === 'string') { try { b = JSON.parse(b); } catch { b = null; } }
  const items = (b && Array.isArray(b.items) ? b.items : []).slice(0, 30)
    .map(i => ({id: String(i && i.id || '').slice(0, 80), size: String(i && i.size || '').slice(0, 12)}))
    .filter(i => i.id);
  if (!items.length) return res.status(400).json({ok: false});
  const stock = await check(items, req.headers['x-forwarded-host'] || req.headers.host);
  res.setHeader('Cache-Control', 'no-store');
  return res.json({ok: true, stock: Object.fromEntries(stock)});
};
