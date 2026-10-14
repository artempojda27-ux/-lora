/* Запис у репозиторій сайту від імені сервера (GH_WRITE_TOKEN у Vercel) — щоб адмінка працювала без токенів. */
const REPO = process.env.ELORA_REPO || 'artempojda27-ux/-lora';
const BRANCH = process.env.ELORA_BRANCH || 'main';

const gh = (path, opt = {}) => fetch(`https://api.github.com/repos/${REPO}/${path}`, {...opt, headers: {
  Authorization: `Bearer ${process.env.GH_WRITE_TOKEN}`, Accept: 'application/vnd.github+json',
  'Content-Type': 'application/json', 'User-Agent': 'elora-admin'}});

/* записати файл (створити або оновити); повтор, якщо файл щойно змінився */
async function putFile(path, text, message) {
  for (let i = 0; i < 3; i++) {
    const cur = await gh(`contents/${path}?ref=${BRANCH}`);
    const sha = cur.ok ? (await cur.json()).sha : undefined;
    const r = await gh(`contents/${path}`, {method: 'PUT', body: JSON.stringify({
      message, branch: BRANCH, content: Buffer.from(text, 'utf8').toString('base64'), ...(sha ? {sha} : {})})});
    if (r.ok) return {ok: true};
    if (r.status !== 409 && r.status !== 422) return {ok: false, status: r.status, error: (await r.text()).slice(0, 200)};
  }
  return {ok: false, status: 409};
}

const dispatch = (workflow, inputs = {}) => gh(`actions/workflows/${workflow}/dispatches`,
  {method: 'POST', body: JSON.stringify({ref: BRANCH, inputs})});

module.exports = {gh, putFile, dispatch, enabled: () => !!process.env.GH_WRITE_TOKEN};
