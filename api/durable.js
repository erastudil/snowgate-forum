/**
 * api/durable.js · private GitHub-backed board state for forum.snowgate.dev
 * token : FORUM_GITHUB_TOKEN
 * repo : FORUM_GITHUB_REPO or erastudil/snowgate-forum-state
 */

const REPO = process.env.FORUM_GITHUB_REPO || 'erastudil/snowgate-forum-state';
const BRANCH = process.env.FORUM_STATE_BRANCH || 'main';
const FILE_PATH = process.env.FORUM_STATE_PATH || 'forum.json';

function authHeaders() {
  return {
    Authorization: 'Bearer ' + process.env.FORUM_GITHUB_TOKEN,
    Accept: 'application/vnd.github+json',
    'User-Agent': 'snowgate-forum',
    'Content-Type': 'application/json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
}

async function gh(url, options) {
  const response = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options && options.headers) },
  });
  return response;
}

function contentsUrl() {
  return 'https://api.github.com/repos/' + REPO + '/contents/' + FILE_PATH;
}

async function readThreads() {
  const response = await gh(contentsUrl() + '?ref=' + encodeURIComponent(BRANCH), { method: 'GET' });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('forum state read failed');
  const body = await response.json();
  const encoded = String(body.content || '').replace(/\s/g, '');
  const parsed = JSON.parse(Buffer.from(encoded, 'base64').toString('utf8'));
  if (!Array.isArray(parsed)) throw new Error('forum state shape invalid');
  return { threads: parsed, sha: body.sha };
}

async function putThreads(threads, sha) {
  const payload = {
    message: 'forum: persist board state',
    content: Buffer.from(JSON.stringify(threads), 'utf8').toString('base64'),
    branch: BRANCH,
  };
  if (sha) payload.sha = sha;
  const response = await gh(contentsUrl(), { method: 'PUT', body: JSON.stringify(payload) });
  if (response.ok) {
    const body = await response.json();
    return { ok: true, sha: body.content.sha };
  }
  if (response.status === 409 || response.status === 422) return { ok: false };
  throw new Error('forum state write failed');
}

async function ensureRepo() {
  const existing = await gh('https://api.github.com/repos/' + REPO, { method: 'GET' });
  if (existing.ok) return;
  if (existing.status !== 404) throw new Error('forum state repo lookup failed');
  const name = REPO.split('/')[1];
  const created = await gh('https://api.github.com/user/repos', {
    method: 'POST',
    body: JSON.stringify({
      name: name,
      private: true,
      auto_init: true,
      description: 'durable thread state for forum.snowgate.dev',
    }),
  });
  if (!created.ok && created.status !== 422) throw new Error('forum state repo create failed');
}

async function hydrate(seedThreads) {
  await ensureRepo();
  const current = await readThreads();
  if (current) return current;
  const seed = Array.isArray(seedThreads) ? seedThreads : [];
  const written = await putThreads(seed, null);
  if (!written.ok) {
    const raced = await readThreads();
    if (raced) return raced;
    throw new Error('forum state seed failed');
  }
  return { threads: seed, sha: written.sha };
}

async function persist(threads, sha, mergeDurable) {
  let payload = threads;
  let currentSha = sha;
  for (let attempt = 0; attempt < 5; attempt++) {
    const written = await putThreads(payload, currentSha);
    if (written.ok) return { sha: written.sha, threads: payload };
    const latest = await readThreads();
    if (!latest) throw new Error('forum state missing during persist');
    payload = mergeDurable(latest.threads, threads);
    currentSha = latest.sha;
  }
  throw new Error('forum persist conflict');
}

module.exports = { hydrate, persist };
