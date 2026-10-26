// Optional independent fallback. Stores only a repository-scoped Actions token.
// No public endpoint, repository writes, manuscript uploads or paid services.
export async function watch(env, fetcher = fetch, now = Date.now()) {
  if (env.ENABLED !== 'true') return { action: 'disabled' };
  if (!env.GITHUB_ACTIONS_TOKEN) throw new Error('Missing repository-scoped Actions token');
  const repo = 'Lmq041/lmq041.github.io';
  const file = 'update-publications.yml';
  const base = `https://api.github.com/repos/${repo}/actions/workflows/${file}`;
  async function request(url, method = 'GET', payload) {
    const response = await fetcher(url, {
      method,
      headers: {
        Authorization: `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'AcademicHomepageIndependentWatchdog',
        'Content-Type': 'application/json',
      },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    });
    if (!response.ok) throw new Error(`GitHub ${method} failed: HTTP ${response.status}`);
    return response.status === 204 ? null : response.json();
  }
  const workflow = await request(base);
  if (workflow.state === 'disabled_manually') return { action: 'respect-manual-disable' };
  if (!['active', 'disabled_inactivity'].includes(workflow.state)) throw new Error('Unexpected workflow state');
  const result = await request(`${base}/runs?branch=main&per_page=20`);
  const runs = result.workflow_runs;
  if (!Array.isArray(runs)) throw new Error('Malformed workflow run response');
  const recent = runs.find(r => ['schedule', 'workflow_dispatch'].includes(r.event));
  const success = runs.find(r => ['schedule', 'workflow_dispatch'].includes(r.event) && r.conclusion === 'success');
  const age = run => now - Date.parse(run.created_at);
  if (recent && !Number.isFinite(age(recent))) throw new Error('Invalid workflow timestamp');
  if (recent && (['queued', 'in_progress', 'waiting', 'pending'].includes(recent.status) || age(recent) < 24 * 3600e3)) {
    return { action: 'recent-run-or-in-progress' };
  }
  // Allow a 31-day month, daylight-saving changes and a grace period before fallback.
  if (success && age(success) < 33 * 86400e3 && workflow.state === 'active') return { action: 'healthy' };
  if (workflow.state === 'disabled_inactivity') await request(`${base}/enable`, 'PUT');
  await request(`${base}/dispatches`, 'POST', { ref: 'main', inputs: { sync: true, publish: true } });
  return { action: 'fallback-dispatched' };
}

export default {
  async scheduled(_controller, env, context) {
    context.waitUntil(watch(env).then(result => console.log(JSON.stringify(result))));
  },
};
