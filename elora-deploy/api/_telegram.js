/* Спільне для функцій Telegram: де шукати id чату для замовлень і перевірка адміна. */

/* TELEGRAM_CHAT_ID має пріоритет; інакше — config/telegram.json, який зберігає адмінка */
async function chatId(req) {
  if (process.env.TELEGRAM_CHAT_ID) return process.env.TELEGRAM_CHAT_ID;
  try {
    const host = req.headers['x-forwarded-host'] || req.headers.host;
    const r = await fetch(`https://${host}/config/telegram.json`, {cache: 'no-store'});
    if (!r.ok) return null;
    const j = await r.json();
    return j && j.chat_id ? String(j.chat_id) : null;
  } catch (e) {
    return null;
  }
}

/* адмін = секретний ключ із посилання на адмінку (ADMIN_KEY у Vercel)
   або власник GitHub-токена з правом запису в репозиторій сайту */
async function isAdmin(req) {
  const k = String(req.headers['x-admin-key'] || ''), want = process.env.ADMIN_KEY || '';
  if (want && k.length === want.length && require('crypto').timingSafeEqual(Buffer.from(k), Buffer.from(want))) return true;
  const auth = req.headers.authorization || '';
  const repo = process.env.ELORA_REPO || 'artempojda27-ux/-lora';
  if (!/^Bearer \S{20,}$/.test(auth)) return false;
  try {
    const r = await fetch(`https://api.github.com/repos/${repo}`,
      {headers: {Authorization: auth, Accept: 'application/vnd.github+json', 'User-Agent': 'elora-admin'}});
    if (!r.ok) return false;
    const j = await r.json();
    return !!(j.permissions && j.permissions.push);
  } catch (e) {
    return false;
  }
}

module.exports = {chatId, isAdmin};
