/* Публікація поста в канал магазину від імені бота (токен — лише тут, у Vercel).
   POST /api/tg-post  {caption, photos: [base64 JPEG, ...]}  ->  {ok, ids}
   Викликає тільки workflow «Пости в Telegram-канал» цього репозиторію: у заголовку
   Authorization — OIDC-токен GitHub Actions (підписаний GitHub, перевіряється за його ключами),
   тож ні секретів у GitHub, ні можливості публікувати від сторонніх. Канал — з config/tg_sources.json. */
const crypto = require('crypto');

const REPO = process.env.ELORA_REPO || 'artempojda27-ux/-lora';
const ISS = 'https://token.actions.githubusercontent.com';
const AUD = 'elora-tg-post';
let jwks = null, jwksAt = 0;

const b64url = s => Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64');

async function verify(jwt) {
  const [h, p, sig] = String(jwt || '').split('.');
  if (!sig) return null;
  const head = JSON.parse(b64url(h)), claims = JSON.parse(b64url(p));
  if (head.alg !== 'RS256') return null;
  if (!jwks || Date.now() - jwksAt > 3600e3) {
    jwks = (await (await fetch(`${ISS}/.well-known/jwks`)).json()).keys; jwksAt = Date.now();
  }
  const jwk = jwks.find(k => k.kid === head.kid);
  if (!jwk) return null;
  const ok = crypto.verify('RSA-SHA256', Buffer.from(`${h}.${p}`), crypto.createPublicKey({key: jwk, format: 'jwk'}), b64url(sig));
  const now = Date.now() / 1000;
  if (!ok || claims.iss !== ISS || claims.aud !== AUD || claims.exp < now || claims.nbf > now + 60) return null;
  if (claims.repository !== REPO || claims.ref !== 'refs/heads/main') return null;
  return claims;
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') return res.status(405).json({ok: false});
  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) return res.status(503).json({ok: false, error: 'not_configured'});
  const claims = await verify((req.headers.authorization || '').replace(/^Bearer\s+/i, '')).catch(() => null);
  if (!claims) return res.status(401).json({ok: false, error: 'auth'});

  let b = req.body;
  if (typeof b === 'string') { try { b = JSON.parse(b); } catch { b = null; } }
  const photos = (b && Array.isArray(b.photos) ? b.photos : []).slice(0, 10);
  const caption = String((b && b.caption) || '').slice(0, 1024);
  if (!photos.length) return res.status(400).json({ok: false, error: 'photos'});

  const host = req.headers['x-forwarded-host'] || req.headers.host;
  const cfg = await fetch(`https://${host}/config/tg_sources.json`).then(r => r.json()).catch(() => null);
  const chat = cfg && cfg.post_to;
  if (!chat) return res.status(503).json({ok: false, error: 'no_channel'});

  const form = new FormData();
  form.append('chat_id', chat);
  const media = photos.map((_, i) => ({type: 'photo', media: `attach://f${i}`, ...(i ? {} : {caption, parse_mode: 'HTML'})}));
  form.append('media', JSON.stringify(media));
  photos.forEach((ph, i) => form.append(`f${i}`, new Blob([Buffer.from(ph, 'base64')], {type: 'image/jpeg'}), `${i}.jpg`));
  const r = await fetch(`https://api.telegram.org/bot${token}/sendMediaGroup`, {method: 'POST', body: form});
  const j = await r.json().catch(() => ({}));
  if (!j.ok) return res.status(502).json({ok: false, error: j.description || 'telegram', code: j.error_code});
  return res.json({ok: true, ids: j.result.map(m => m.message_id)});
};
