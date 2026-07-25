# Load testing

[k6](https://grafana.com/docs/k6/latest/) scenarios that turn pool sizes, rate
limits and timeout tuning from guesses into measurements. `script.js` exercises
the health probe and the `{{ cookiecutter.first_entity }}` CRUD cycle
(create → get → patch → list → delete){% if cookiecutter.use_auth == "yes" %} with a bearer token obtained in `setup()`{% endif %}.

## Prerequisites

- [k6 installed](https://grafana.com/docs/k6/latest/set-up/install-k6/)
  (`brew install k6`), or run it from Docker:
  `docker run --rm -i --network host grafana/k6 run -e BASE_URL=http://localhost:8000 - < loadtest/script.js`
- The API running with its dependencies: `make run`{% if cookiecutter.use_docker == "yes" %} or `make docker-up`{% endif %}.
{%- if cookiecutter.use_rate_limiting == "yes" %}
- Raise the rate limit for the run (e.g. `RATE_LIMIT=100000/minute`) — all
  virtual users share one client IP, so the default limit answers 429 long
  before the service is actually saturated.
{%- endif %}

## Running

```bash
make loadtest                                # both scenarios vs http://localhost:8000
BASE_URL=https://staging.example.com make loadtest
k6 run -e SCENARIO=smoke loadtest/script.js  # just the smoke scenario
```

## Scenarios and thresholds

| Scenario | Shape                                  | Purpose                        |
| -------- | -------------------------------------- | ------------------------------ |
| `smoke`  | 5 VUs for 30s                          | Sanity gate; gross regressions |
| `ramp`   | 0 → 25 → 50 → 0 VUs over 2 minutes     | Capacity under growing load    |

The run fails if the error rate reaches 1%, health p95 exceeds 100 ms, or CRUD
p95 exceeds 500 ms. Adjust the thresholds in `script.js` as the service earns
real numbers.
{%- if cookiecutter.use_auth == "yes" %}

`setup()` registers `loadtest@example.com` (idempotent — an existing user is
fine) and logs in; override with `-e LOADTEST_EMAIL=... -e LOADTEST_PASSWORD=...`
when registration is closed. Never point this at production with real
credentials in your shell history.
{%- endif %}
