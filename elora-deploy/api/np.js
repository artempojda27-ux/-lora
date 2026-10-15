/* Нова пошта для оформлення замовлення: підказки міст і відділень із довідника НП.
   GET /api/np?city=біла        -> {ok, list:[{name, ref, n}]}  (ref — місто доставки, n — кількість відділень)
   GET /api/np?wh=<ref>&q=12    -> {ok, list:[{name, num}]}     (відділення та поштомати, що працюють)
   Довідник НП відкритий; ключ NP_API_KEY у Vercel не обов'язковий. */
const API = 'https://api.novaposhta.ua/v2.0/json/';

async function np(modelName, calledMethod, methodProperties) {
  const r = await fetch(API, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({apiKey: process.env.NP_API_KEY || '', modelName, calledMethod, methodProperties})});
  const j = await r.json();
  if (!j.success) throw new Error((j.errors || []).join('; ') || 'np');
  return j.data;
}

module.exports = async (req, res) => {
  const q = req.query || {};
  const str = v => typeof v === 'string' ? v.trim().slice(0, 60) : '';
  try {
    if (q.city != null) {
      const name = str(q.city);
      if (name.length < 2) return res.json({ok: true, list: []});
      const d = await np('Address', 'searchSettlements', {CityName: name, Limit: '12', Page: '1'});
      const list = ((d[0] && d[0].Addresses) || []).filter(a => a.DeliveryCity && +a.Warehouses > 0)
        .map(a => ({name: a.Present, ref: a.DeliveryCity, n: +a.Warehouses}));
      res.setHeader('Cache-Control', 'public, max-age=3600, s-maxage=86400');
      return res.json({ok: true, list});
    }
    if (q.wh != null) {
      const ref = str(q.wh);
      if (!/^[0-9a-f-]{36}$/i.test(ref)) return res.status(400).json({ok: false, error: 'ref'});
      const d = await np('AddressGeneral', 'getWarehouses', {CityRef: ref, FindByString: str(q.q), Limit: '40', Page: '1'});
      const list = d.filter(w => w.WarehouseStatus === 'Working')
        .map(w => ({name: w.Description, num: w.Number}));
      const want = str(q.q);            // введено номер — спершу саме це відділення
      if (/^\d+$/.test(want)) list.sort((a, b) => (b.num === want) - (a.num === want));
      res.setHeader('Cache-Control', 'public, max-age=3600, s-maxage=21600');
      return res.json({ok: true, list});
    }
    return res.status(400).json({ok: false, error: 'query'});
  } catch (e) {
    console.error('np', e);
    return res.status(502).json({ok: false, error: 'np'});
  }
};
