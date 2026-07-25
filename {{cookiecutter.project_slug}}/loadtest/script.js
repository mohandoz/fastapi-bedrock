// k6 load test: smoke + ramp scenarios against health and {{ cookiecutter.first_entity }} CRUD.
//
//   make loadtest                                  # both scenarios, http://localhost:8000
//   k6 run -e BASE_URL=https://staging.example.com loadtest/script.js
//   k6 run -e SCENARIO=smoke loadtest/script.js    # a single scenario
//
// See loadtest/README.md for prerequisites.

import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API = `${BASE_URL}/api/v1`;
{%- if cookiecutter.use_auth == "yes" %}
const EMAIL = __ENV.LOADTEST_EMAIL || 'loadtest@example.com';
const PASSWORD = __ENV.LOADTEST_PASSWORD || 'loadtest-password-123';
{%- endif %}

const scenarios = {
  // Sanity: a handful of users for a short burst; catches gross regressions.
  smoke: {
    executor: 'constant-vus',
    vus: 5,
    duration: '30s',
    exec: 'crud',
  },
  // Capacity: ramp up, hold, then back off; starts after the smoke run.
  ramp: {
    executor: 'ramping-vus',
    startTime: '35s',
    startVUs: 0,
    stages: [
      { duration: '30s', target: 25 },
      { duration: '1m', target: 50 },
      { duration: '30s', target: 0 },
    ],
    exec: 'crud',
  },
};

const only = __ENV.SCENARIO;
export const options = {
  scenarios: only ? { [only]: { ...scenarios[only], startTime: '0s' } } : scenarios,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{endpoint:health}': ['p(95)<100'],
    'http_req_duration{endpoint:crud}': ['p(95)<500'],
  },
};

export function setup() {
{%- if cookiecutter.use_auth == "yes" %}
  // Best effort: the user may already exist from a previous run.
  http.post(`${API}/auth/register`, JSON.stringify({ email: EMAIL, password: PASSWORD }), {
    headers: { 'Content-Type': 'application/json' },
  });
  // OAuth2 password flow: form-encoded username/password.
  const login = http.post(`${API}/auth/login`, { username: EMAIL, password: PASSWORD });
  if (login.status !== 200) {
    throw new Error(`login failed with ${login.status}; is the API running at ${BASE_URL}?`);
  }
  return { token: login.json('access_token') };
{%- else %}
  const health = http.get(`${API}/health`);
  if (health.status !== 200) {
    throw new Error(`health check failed with ${health.status}; is the API running at ${BASE_URL}?`);
  }
  return {};
{%- endif %}
}

function requestParams(data, endpoint) {
  const headers = { 'Content-Type': 'application/json' };
  if (data.token) {
    headers['Authorization'] = `Bearer ${data.token}`;
  }
  return { headers, tags: { endpoint } };
}

export function crud(data) {
  group('health', () => {
    const res = http.get(`${API}/health`, { tags: { endpoint: 'health' } });
    check(res, { 'health is 200': (r) => r.status === 200 });
  });

  group('{{ cookiecutter.first_entity }} crud', () => {
    const params = requestParams(data, 'crud');
    const name = `k6-${__VU}-${__ITER}-${Date.now()}`;

    const created = http.post(
      `${API}/{{ cookiecutter.first_entity }}s`,
      JSON.stringify({ name, description: 'created by the k6 load test' }),
      params,
    );
    if (!check(created, { 'create is 201': (r) => r.status === 201 })) {
      return; // no point exercising the rest of the cycle without an id
    }
    const id = created.json('id');

    const fetched = http.get(`${API}/{{ cookiecutter.first_entity }}s/${id}`, params);
    check(fetched, { 'get is 200': (r) => r.status === 200 });

    const updated = http.patch(
      `${API}/{{ cookiecutter.first_entity }}s/${id}`,
      JSON.stringify({ name: `${name}-updated` }),
      params,
    );
    check(updated, { 'update is 200': (r) => r.status === 200 });

    const listed = http.get(`${API}/{{ cookiecutter.first_entity }}s?limit=20`, params);
    check(listed, { 'list is 200': (r) => r.status === 200 });

    const deleted = http.del(`${API}/{{ cookiecutter.first_entity }}s/${id}`, null, params);
    check(deleted, { 'delete is 204': (r) => r.status === 204 });
  });

  sleep(1);
}
