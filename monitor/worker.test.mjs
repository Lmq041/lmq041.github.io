import assert from 'node:assert/strict';
import test from 'node:test';
import { watch } from './worker.mjs';

const now = Date.parse('2026-10-26T12:00:00Z');
const env = { ENABLED: 'true', GITHUB_ACTIONS_TOKEN: 'test-only' };
function fake(state, runs) {
  const calls = [];
  const fetcher = async (url, init) => {
    calls.push({ url, ...init });
    return { ok: true, status: init.method === 'GET' ? 200 : 204,
      json: async () => url.includes('/runs?') ? { workflow_runs: runs } : { state } };
  };
  return { calls, fetcher };
}
test('disabled configuration performs no network access', async () => {
  const f = fake('active', []);
  assert.equal((await watch({ ENABLED: 'false' }, f.fetcher, now)).action, 'disabled');
  assert.equal(f.calls.length, 0);
});
test('healthy monthly run produces no dispatch after 25 days', async () => {
  const f = fake('active', [{ event: 'schedule', status: 'completed', conclusion: 'success', created_at: '2026-10-01T07:17:00Z' }]);
  assert.equal((await watch(env, f.fetcher, now)).action, 'healthy');
  assert.equal(f.calls.length, 2);
});
test('monthly fallback allows a long month but dispatches after 33 days', async () => {
  const f = fake('active', [{ event: 'schedule', status: 'completed', conclusion: 'success', created_at: '2026-09-24T12:00:00Z' }]);
  assert.equal((await watch(env, f.fetcher, now)).action, 'healthy');
  assert.equal(f.calls.length, 2);
  const stale = fake('active', [{ event: 'schedule', status: 'completed', conclusion: 'success', created_at: '2026-09-22T12:00:00Z' }]);
  assert.equal((await watch(env, stale.fetcher, now)).action, 'fallback-dispatched');
  assert.equal(stale.calls[2].method, 'POST');
});
test('inactivity-disable is enabled and dispatched once', async () => {
  const f = fake('disabled_inactivity', []);
  assert.equal((await watch(env, f.fetcher, now)).action, 'fallback-dispatched');
  assert.equal(f.calls[2].method, 'PUT');
  assert.equal(f.calls[3].method, 'POST');
  assert.equal(JSON.parse(f.calls[3].body).inputs.publish, true);
});
test('manual disable is never overridden', async () => {
  const f = fake('disabled_manually', []);
  assert.equal((await watch(env, f.fetcher, now)).action, 'respect-manual-disable');
  assert.equal(f.calls.length, 1);
});
test('recent dispatch is not duplicated', async () => {
  const f = fake('active', [{ event: 'workflow_dispatch', status: 'in_progress', created_at: '2026-10-26T10:20:00Z' }]);
  assert.equal((await watch(env, f.fetcher, now)).action, 'recent-run-or-in-progress');
});
test('GitHub failures surface and do not pretend success', async () => {
  await assert.rejects(watch(env, async () => ({ ok: false, status: 401 }), now), /HTTP 401/);
});
