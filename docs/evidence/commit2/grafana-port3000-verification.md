# Grafana port 3000 standardization and documentation sync

Verified: 2026-10-16T15:46:18.298863+00:00. Repository `GreenShop-Official`, branch `main`, M1 baseline `af1abea`. No commit or push.

## Result and cause

Main Grafana listens on container port 3000 and Ubuntu publishes only `127.0.0.1:3000:3000`. Prometheus remains `127.0.0.1:9090:9090`. Port 13000 was not a Grafana setting in source or rendered runtime; a Windows SSH tunnel can select its own local port. The previous source/default and Main browser root URL were **localhost:1300**, distinct from 13000. The root URL is now **http://localhost:3000/**. No Docker port mapping or internal datasource address changed.

Use VS Code Remote SSH → TERMINAL → PORTS → Forward a Port → **3000**, open its actual Forwarded Address and sign in. Usually this is `http://localhost:3000/`; forward 9090 for Prometheus. The operator confirms this Windows method works. This VM cannot independently observe the Windows PORTS tab/browser, so a new independent Windows-client check is **NOT TESTED**. Server HTTP/API/real Chromium form login and dashboards were verified. Alternate local port conflicts are client-side; see the monitoring guide for the optional SSH fallback.

## Changes and deployment

- `README.md`: corrected Official clone URL, Main project/private-plan instructions, ten migrations and current review-index semantics, current M2 services/networks/status, core fresh-install metrics-token prerequisite, Grafana/Prometheus access, credentials guidance, dashboards/rules and limitations. Preserved M1 content with its old acceptance recipe clearly marked historical.
- `monitoring/README.md`: primary VS Code access, three port layers, optional SSH fallback, links to configuration, troubleshooting, QA first-run versus repeat-test preconditions and one-time rollout warning. Consolidated duplicate access directions.
- `.env.example` and `docker-compose.yml`: default browser URL changed from localhost:1300 to localhost:3000. Existing loopback bindings remain unchanged. No alert rule, dashboard, contact point, exporter or scrape source was edited.
- Evidence: this report, the structured verification JSON and two genuine screenshots; appended follow-up links to the existing acceptance/audit reports and refreshed the evidence hash manifest. No original evidence/test/deployment file was deleted or overwritten.

The existing QA was tested first, including Grafana/Prometheus restart persistence. Main then received one environment-value change in its authoritative private Compose plan. Only Main Grafana was stopped/recreated with the existing project/image/volume/secrets and `--no-deps`. Before replacement, its offline data tar and original plan were saved outside Git; the copied SQLite database passed `integrity_check`. Restore the private `compose-before.json` to the authoritative Main plan and recreate only Grafana to revert the URL. No SQL restore or volume reset is part of rollback.

On restart, current unchanged provisioning reloads relative runbook links over historical absolute localhost links. Their destination path is unchanged; this is documented normalization, not an alert-condition/PromQL change. Comparison excludes provisioning timestamps and normalizes only those known local runbook URL hosts. All other rule data, UIDs, dashboards, datasource, contact points and routing policy were compared.

## Verification

- Main and QA: valid Compose, existing project/container/volume names retained, no duplicate service or new project. Grafana and Prometheus healthy, loopback bindings retained; exporters/receiver unpublished.
- Grafana: authenticated API and actual Chromium login on Main and QA; anonymous API and default password rejected; existing configured password retained. Three dashboards rendered and every provisioned panel expression returned actual series. Datasource health OK. Four evaluated rules healthy and Normal; contact point/policy retained.
- Prometheus: five targets UP on each environment; actual MySQL, Nginx, cAdvisor, ASP.NET and security metric families present; historical security series available. QA dashboard/rule/TSDB persistence passed after restart; Main Prometheus was not restarted.
- QA security: Customer/Admin sign-in and authorization checks, missing-CSRF rejection, four actual failed credentials remain Normal, fifth within 60 seconds produces Firing and a real receiver notification, followed by automatic Normal/Resolved notification. Threshold/security mechanisms unchanged; no burst on Main.
- Main: HTTPS home/catalog/readiness and both login pages 200; public metrics/stub_status 404 and direct unauthenticated application metrics 404. Table hashes, migration IDs, uploads, Data Protection keys, TLS and all four core container IDs/images/mounts unchanged. Main Customer/Admin authenticated flows remain **NOT TESTED** because no safe test credentials are available.
- Docs: local links and Bash/Python syntax checked; secret generation tested silently in temporary directories, permissions verified and rerun refused without overwriting. Fresh-install Compose core/all-profile render valid; no new installation/project was started.

An initial strict comparison flagged runbook URL representation after QA restart. That was investigated and the equivalent path normalization above applied to verification. A preliminary full-container Main guard also stopped before mutation; an immediate reread matched the baseline. Its comparison now canonicalizes Docker mount ordering by destination while retaining every identity/image/mount/health check. Both checks passed before deployment continued. No failure was bypassed by weakening authentication or changing runtime rules.

## Screenshots and evidence

[Main infrastructure after port-3000 update](grafana-main-port3000.png) shows actual Main target status and container metrics. [QA recovery](grafana-qa-recovery.png) shows the rendered rule title, actual Normal state and unchanged condition. Its optional graph plugin was still loading at capture time; notification delivery/recovery is established by the structured test as well as the visible state, not by a rendered graph.

The original blank `security-alert-resolved.png` and historical `grafana-access-update.json` remain unchanged and explicitly historical. Earlier reports retain capture-time URLs. No screenshot pixels were edited. Both new images were opened for disclosure review; they contain no credential, cookie, authorization header or private customer record.

## Pre-commit status

Reviewed all **80 staged files** (64 text files, 16 screenshots). No known live secret, API key, private key, authorization/session value or private customer data found. All scanner candidates were reviewed as environment references/placeholders/descriptive access metadata. Original screenshots match their reviewed hashes; both new screenshots were visually inspected and PNG metadata checked. `.gitignore` tests passed for 16 private paths and 3 intentional exceptions. Evidence manifest verified. No TXT trailing whitespace found; `git diff --cached --check` passed.

```text
GRAFANA_PORT_3000: PASS
OBSOLETE_PORT_13000_DOCS: CLEAN
README_SYNC: PASS
MONITORING_README_SYNC: PASS
GRAFANA_DASHBOARDS: PASS
PROMETHEUS: PASS
ALERT_RULES: PASS
DATA_PRESERVATION: PASS
SECURITY_AUDIT: PASS
GIT_DIFF_CHECK: PASS
COMMIT_2_READY: YES
```

Readiness covers the staged Commit 2 and the stated verification scope; Main application authenticated flows and independent Windows-client rechecking remain NOT TESTED as explained above. Existing cAdvisor Docker-socket trust and the QA-only notification sink limitations remain documented in the monitoring guide.

Runtime details: [structured verification](grafana-port3000-verification.json). Prior acceptance and operational limits: [Commit 2 verification](commit2-verification.md), [security audit](precommit-security-audit.md). No Main application credentials were created or reset. No Git history was changed.
