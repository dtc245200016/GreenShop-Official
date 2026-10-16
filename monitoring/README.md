# GreenShop Monitoring — Milestone 2

ASP.NET Core uses prometheus-net.AspNetCore 8.2.1. Prometheus scrapes every 10s and stores at most 3 days / 512 MB. Grafana OSS provisions three dashboards, four automatic rules, a webhook contact point and routing policy from Git. No Grafana Cloud, paid plugin or Loki/Promtail is required.

## Deployment and data safety

The audited Main project is `dtc245200016_btl_tkqt_htpm`, originally started from `/home/trung/DTC245200016_BTL_TKQT_HTPM`. **Do not run an unqualified `docker compose up` from this repository against Main.** It could create a different project and empty database. Read the actual run result in [the M2 verification report](../docs/evidence/commit2/commit2-verification.md) before deploying.

Main volumes: `dtc245200016_btl_tkqt_htpm_mysql_data`, `dtc245200016_btl_tkqt_htpm_product_images`, `dtc245200016_btl_tkqt_htpm_data_protection_keys`. Preserve original TLS bind directory. Never use `down -v`, reset data, remove volumes, or change database passwords to install monitoring. The source adds no EF migration.

`tests/monitoring/acceptance.py` creates the explicitly named project `greenshop-m2-qa`. Its private rendered Compose file, independent secrets, certificate, accounts and backups live outside Git in `~/.local/share/greenshop-monitoring/`. The generated Compose is an operational QA artifact, derived from the single repository Compose. It has no Main networks or volumes. QA splits application, database and internal monitoring networks. Main retains its audited legacy application/database network; only the MySQL exporter bridges it to the internal monitoring network. Prometheus and Grafana do not join the database network.

## Resources and services

Reserve approximately 1.5–2 GB RAM and 3 GB disk for QA with monitoring, in addition to existing Main services and image caches. Prometheus is limited to 384 MB, Grafana 384 MB, cAdvisor 256 MB, exporters 64/48 MB, the QA sink 32 MB. CPU limits prevent monitoring from monopolizing the four-vCPU VM. Node Exporter is deliberately omitted on this VM. There is no fabricated host CPU/memory panel.

Pinned image versions are in `docker-compose.yml`. cAdvisor mounts host filesystem metadata and `/var/run` read-only to discover cgroups v2 and Docker containers. It runs without privileged mode and drops all capabilities. **A read-only bind of a Unix socket still allows Docker API calls**: do not treat `:ro` as API authorization. This collector must remain on an internal network, inaccessible to customers. Its access is a remaining trust boundary. cAdvisor container last-seen is freshness, not a Docker restart counter; no restart-count metric is claimed.

## Secrets

Set `MONITORING_SECRETS_DIR` to a private absolute directory outside Git. Create it with mode 0700. Store randomly generated `metrics-token` and `grafana-password`, plus `mysql-exporter.cnf` using the `[client]` section and a dedicated exporter user. Use Docker Compose file-backed secrets. Files are readable in only the containers mounting them; the 0700 parent prevents other local users reading them. Never put their values in `.env.example`, logs, command arguments, screenshots or documentation. The runner generates them without printing values.

The exporter account has `PROCESS` and `MAX_USER_CONNECTIONS 3`; collectors requiring replication or application SELECT are disabled. It has no DML/DDL privileges and cannot read application tables. It connects using `--config.my-cnf`, not deprecated DATA_SOURCE_NAME. Validate actual grants and denied writes in QA.

Grafana username is `admin`. Its initial random password is mounted through `GF_SECURITY_ADMIN_PASSWORD__FILE`. Anonymous access and signup are disabled. The password secret bootstraps an empty Grafana volume; changing it does not reset an existing Grafana account. Change the password through the authenticated user profile (or the official Grafana administration procedure); do not delete the volume. Read secrets only on the VM in a private session, never paste them into chat. Cookies use SameSite Strict; Secure=false is intentional for loopback HTTP over an SSH tunnel. Set Secure=true if moving Grafana behind HTTPS.

## Start isolated QA and verify

The sequence below is the **initial pre-deployment acceptance** on a clean QA workspace. It is not a replay command for the existing Main/QA installation. Install pinned dependencies from `tests/monitoring/requirements.txt` in a venv.

Python dependencies: requests, PyYAML, bcrypt, Playwright; Chromium must be installed for screenshots. .NET SDK 8 and Docker Compose are required. Run from the official repository with Docker access:

```bash
python3 tests/monitoring/acceptance.py prepare
python3 tests/monitoring/acceptance.py backup
python3 tests/monitoring/acceptance.py start
python3 tests/monitoring/acceptance.py verify
python3 tests/monitoring/acceptance.py preservation
python3 tests/monitoring/acceptance.py screenshots
python3 tests/monitoring/acceptance.py incident
```

`verify` expects the clean initial login-failure counter to be zero; it is not a general post-incident health check. `preservation` compares pre-M2 Main container IDs and belongs before Main rollout; web/Nginx IDs legitimately change during deployment. Use `main_smoke.py` for post-deployment read-only Main checks. On existing QA, use the targeted regression/incident tools below and inspect their preconditions instead of rerunning initial setup.

`prepare` refuses to overwrite an existing QA configuration. `backup` refuses to overwrite a backup. `start` is the first-run build/start/restore verification, not a restart command. Keep the private directory on persistent VM storage, not /tmp. Backups contain sensitive customer data and keys; restrict access and remove them only under an explicit operator retention policy. Do not upload them as evidence.

The isolated QA ports are Grafana `127.0.0.1:21300`, Prometheus `127.0.0.1:21990`, HTTPS `127.0.0.1:21543`. The standard monitoring configuration uses Grafana `127.0.0.1:3000` and Prometheus `127.0.0.1:9090`. Exporters and the receiver publish no host port. MySQL has no QA host port.

## Windows access

Use **VS Code Remote SSH → TERMINAL → PORTS → Forward a Port → 3000** as the primary Main Grafana access method. Open the displayed **Forwarded Address**, normally `http://localhost:3000/`, then sign in with the configured local Grafana OSS account. Grafana Cloud is not required. If VS Code selects a different local port because 3000 is occupied, use that actual address. Forward remote **9090** for Prometheus, normally `http://localhost:9090/`.

Grafana listens on container port 3000. Main publishes only Ubuntu `127.0.0.1:3000`; the Windows local port belongs to the forwarding client. `GF_SERVER_ROOT_URL` / `GRAFANA_PUBLIC_URL` is `http://localhost:3000/` for canonical browser links, independently of `GRAFANA_PORT`, the Ubuntu host binding. An alternate local port may require a separate deliberate root-URL decision for generated links; it does not require changing the container port or exposing Grafana publicly. QA keeps remote ports 21300 (Grafana), 21990 (Prometheus), 21543 (website); forward those only when accessing QA.

Optional SSH fallback, replacing the example IP with the current VM IP:

```powershell
ssh -N -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 trung@192.168.197.128
```

The number before the first colon is the Windows port chosen by the operator. Keep the SSH terminal open. A separate tunnel is unnecessary when VS Code already forwards the same ports; duplicate local bindings can conflict. A historical Windows port 13000 was a client-side option, not a Grafana service port, and is not required. Do not change Main/QA bindings to work around a Windows port conflict.

If forwarding fails, confirm the Remote SSH session is connected to the correct VM, inspect the PORTS tab and the actual Forwarded Address, then check `curl --fail http://127.0.0.1:3000/api/health` on Ubuntu. Check local port conflicts/firewall/SSH separately from container health. Server-side checks cannot independently verify a Windows browser session; the operator reports that VS Code port 3000 access works.

## Metrics and dashboards

Configuration links: [dashboards](grafana/dashboards/), [dashboard provider](grafana/provisioning/dashboards/dashboards.yml), [datasource](grafana/provisioning/datasources/prometheus.yml), [alert rules](grafana/provisioning/alerting/rules.yml), [contact point/policy](grafana/provisioning/alerting/notifications.yml), [Prometheus scrapes](prometheus/prometheus.yml). Dashboards:

* Infrastructure Overview: target status, real container CPU/RAM/network/freshness, Nginx connections, MySQL availability and connections.
* Application & Database: request rate, histogram P50/P95, 4xx/5xx, fixed endpoint groups, MySQL running threads/queries and scrape availability.
* Security Monitoring: initialized failure/success/denial counters, exact rolling failures, sampled 5m estimate, condition and actual Grafana alert list.

Prometheus `/api/v1/targets` must show every target UP. Query each metric used by a panel; target UP alone is insufficient. Counter rates need two or more samples. P50/P95 require actual requests; no requests means an undefined quantile, not a made-up latency. The runner produces real login and health requests.

Nginx OSS stub_status provides connections and aggregate HTTP request counters, **not 4xx/5xx**. Status rates come from application instrumentation. The app endpoint requires a constant-time checked bearer token and is blocked at public Nginx; no auth redirect. Tokens, PII, raw paths, URLs and query strings are never metric labels. Route groups are a fixed allowlist. `up{job="greenshop"}` measures scrape availability; `/health/ready` independently checks real database access.

## GS-SEC-001

Each actual invalid-credential rejection increments `greenshop_auth_login_failures_total` once. GET login, invalid form, CSRF rejection, successful login, disabled accounts and portal role mismatch do not increment it. Portal role mismatches count as authorization denials. Security events are JSON console logs: `auth.login.failed`, `auth.login.succeeded`, `auth.access.denied`, with UTC, request ID, fixed route group, safe actor type, reason and service. No password, cookie, token, account ID, email or IP is included.

The exact rolling gauge `greenshop_auth_login_failures_last_60s` counts actual credential rejections in the current process, using monotonic timestamps. It prunes on scrape and login; initialized at zero. Grafana evaluates every 10s, with no pending delay:

```promql
sum(greenshop_auth_login_failures_last_60s) >= bool 5
```

A Grafana threshold `A > 0` turns this boolean into the alert. The value **5 is not lowered to 4**. `sum(increase(greenshop_auth_login_failures_total[1m])) >= 5` is a sampled diagnostic alternative, not the authoritative event threshold, because extrapolation and scrape boundaries affect it. The five-minute dashboard uses increase and is explicitly an estimate.

This is aggregate suspicious password guessing, not proof of one attacking user/IP or successful compromise. The deployment has one web process. Counters/window reset on process restart; a failed scrape or outage can miss a short transient. Multiple replicas would need a shared event window to claim an exact cross-instance threshold. A burst of exactly five failures must be observed before the oldest event leaves its 60s window; the controlled QA test sends all five quickly. Notification latency includes scrape, evaluation and delivery; it is not instantaneous.

The runner submits valid anti-CSRF forms for a synthetic QA Customer, verifies +5 and window=5, waits for actual Grafana FIRING, checks the receiver's real payload, waits for NORMAL and a resolved notification, then repeats with a clean window. Existing rate limits remain enabled and unchanged. It never performs the burst on Main.

Additional alerts: WebDown = scrape down for 20s; MySQLDown = mysql_up <1 for 20s; HighHttp5xxRate = >5% of completed HTTP requests over 2m, pending 1m. Low traffic can make a ratio sensitive; review request counts before diagnosing. Grafana NoData/error alerts fail visibly rather than silently claim healthy.

## Notifications

`GreenShop Security Alerts` routes by alert name/incident, no group wait, 10s group interval, 4h repeat. The internal QA webhook stores at most 100 real notifications in memory and stdout, with UTC receipt time and full Grafana-generated status, labels, incident, severity, summary and link. It is an acceptance sink, not an operational production pager. It publishes no host port. Restart loses its in-memory history; sanitized evidence is saved before restart. The default contact URL is internal and can be overridden by QA_WEBHOOK_URL. External channels are optional and must store credentials locally. A test notification button is insufficient proof.

## Restart and rollback

Use the existing rendered QA Compose and explicit project: `docker compose -p greenshop-m2-qa -f ~/.local/share/greenshop-monitoring/qa/compose.json restart grafana prometheus`. Check dashboards, alert rules, counters, TSDB and MySQL data afterward. Do not reset Grafana storage to repair auth.

`scripts/deploy-monitoring.py` was the one-time M1-to-M2 rollout for this audited deployment. It refuses an existing Main plan; do not delete that plan or rerun it as a routine updater.

Before Main deploy, require build, QA, backup restore, Main baseline and preservation PASS. Main deployment requires an audited service-specific plan preserving project name, DB volume, upload/key volumes, TLS and current environment. Never recreate DB/phpMyAdmin to add telemetry. Keep the old web image and Nginx config privately for rollback. Roll back web image/config under the same Compose project and mounts; validate Nginx before reload; stop added monitoring services only. Do not restore SQL over a running database as routine rollback; source has no schema changes.

## Troubleshooting and Commit 3

Targets down: inspect DNS/network membership, secret mount readability, bearer token match, exporter account/grants and Nginx internal status. Use `compose config --quiet`; rendered config can contain secrets and must not be printed. cAdvisor requires cgroups v2 and readable Docker metadata; verify labeled container metrics before accepting panels. Grafana startup failures: inspect provisioning validation errors, datasource UID and 10s alert scheduler setting. An existing volume retains its old admin password.

No Docker restart counter, host Node Exporter data, Nginx status-code histogram or Loki query is claimed. Commit 3 can collect the existing JSON stdout events and correlate UTC/request_id with GS-SEC-001 without changing login instrumentation. Apply log retention/access control before centralized collection.

## Current deployment and repeatable tools

Main monitoring was deployed under the original project. Use the audited private runtime file, never an unqualified Compose command:

```bash
docker compose -p dtc245200016_btl_tkqt_htpm -f ~/.local/share/greenshop-monitoring/main/compose.json ps
```

Install test dependencies into an isolated environment with `python3 -m pip install -r tests/monitoring/requirements.txt` and `python3 -m playwright install chromium`. Use a venv; no system Python replacement is required. On this VM the browser tooling used for acceptance is in `/tmp/greenshop-m2-python`; the installed Chromium executable is `/tmp/greenshop-continue-browsers/chromium-1248/chrome-linux64/chrome`. These temporary tools may need reinstalling after reboot. To use the existing installation:

```bash
export PYTHONPATH=/tmp/greenshop-m2-python
export CHROMIUM_EXECUTABLE=/tmp/greenshop-continue-browsers/chromium-1248/chrome-linux64/chrome
python3 tests/monitoring/capture.py
```

`capture.py` preloads the real Grafana browser, submits five actual invalid-credential forms on QA, waits for rendered value 5 and Firing, captures the direct internal receiver payload, then waits for recovery. It is useful on a slow VM where capturing a dashboard immediately after navigation can catch loading placeholders. `acceptance.py boundary` verifies four failures remain Normal before the fifth causes Firing. Both keep the actual threshold and security controls unchanged.

Additional QA checks: `regression.py regression|grants|archives|persistence`; `engagement.py` exercises checkout, real Admin order transitions, reviews/replies and SignalR; `faults.py faults` exercises outages only on QA. `faults.py rollback` uses the saved pre-M2 rollback image when it exists. `main_smoke.py` runs read-only Main checks and Grafana UI verification; it never authenticates a Main Customer/Admin. Do not overlap outage, restart and incident scripts on the same QA project.

Main backups/rollback plans and secrets remain in the persistent private directory; temporary Python/browser tooling is separate. After a failed test, inspect private errors and verify service health before retrying.

## Current credentials and historical evidence

The Main Grafana username remains `admin`. The operator's custom password is stored only in the existing private secret/metadata files outside Git. This access cleanup does not reset it. Startup secrets alone do not change an existing Grafana account. Credentials are local to Grafana OSS, separate from website accounts; no Grafana Cloud login is needed.

Historical screenshots and `grafana-access-update.json` retain their original capture-time URLs. Current access and verification are recorded separately; historical URLs are not instructions for the current deployment. The original blank resolved screenshot is documented in the acceptance report; notification JSON remains valid recovery evidence.
