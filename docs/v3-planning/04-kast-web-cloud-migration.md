# Phase D — kast-web cloud migration design

This document is the implementation plan for Phase D of the kast v3 refactor: moving the cloud-deployment subsystem from kast to kast-web. It supersedes the brief Phase D summary in `03-design-and-migration.md` once that exploration revealed the migration is more re-architecture than file-relocation.

## Where we are

- kast is on `refactor/v3.0`. Phase A (foundation refactors), Phase B (CLI modernization), Phase C1+C3+C4 (AI exec summary), and Phase D9 (cloud-mode deprecation warning) have all shipped on that branch.
- kast-web is on `refactor/v2.0` (its v1.5 → v2.0 refactor). Phase D1–D8 + D11 land there.
- The two repos release as a coordinated bundle: kast 3.0 + kast-web 2.0.

## The re-architecture

The original Phase D plan in `03-design-and-migration.md` framed the work as "move ~2,452 lines of cloud subsystem from kast to kast-web." That's incomplete. The exploration of kast-web revealed:

**Today's flow (kast-web v1.5):**

```
kast-web execute_scan_task (app/tasks.py)
  -> reads ZapConfiguration from DB, decrypts cloud_config
  -> sets AWS_/AZURE_/GOOGLE_ env vars from creds
  -> subprocess.Popen([kast, --target X, --set zap.execution_mode=cloud, ...])
       └─ kast.zap_plugin (cloud mode)
            └─ ZapProviderFactory.create_provider() → CloudZapProvider
            └─ TerraformManager.provision()       (in kast)
            └─ SSHExecutor bootstrap              (in kast)
            └─ ZAPAPIClient connects              (in kast)
            └─ Run scan via ZAP automation
            └─ TerraformManager.destroy()
```

The current architecture has **kast-web as the credential vault** and **kast as the cloud runtime.** That's exactly the inversion v3 wants to fix. kast is a CLI; it shouldn't manage long-running infrastructure.

**Phase D target flow (kast-web v2.0 + kast 3.0):**

```
kast-web execute_scan_task
  ├─ kastweb.cloud.orchestrator.provision(scan, target)
  │   ├─ TerraformManager (now in kast-web)
  │   └─ SSHExecutor       (now in kast-web)
  │   └─ Returns: {zap_url, zap_api_key, instance_id}
  ├─ subprocess.Popen([
  │     kast, --target X,
  │     --set zap.execution_mode=remote,
  │     --set zap.remote.url=<zap_url>,
  │     --set zap.remote.api_key=<zap_api_key>,
  │     ...
  │   ])
  │     └─ kast.zap_plugin (REMOTE mode — already supported)
  │         └─ Connects to provisioned ZAP, runs scan, returns
  └─ kastweb.cloud.orchestrator.teardown(instance_id)
      └─ TerraformManager.destroy()
```

Key insight: kast already supports remote mode (connect to an existing ZAP via URL + API key). Phase D leverages it. The cloud-mode code path in kast.zap_plugin and `kast.scripts.zap_*` becomes dead code — D10 deletes it after D1–D8 ship.

## What changes in each repo

### kast (this repo)

- **D9 — LANDED** on `refactor/v3.0` commit `7e25c6a`. Cloud mode emits a `DeprecationWarning` + console banner.
- **D10 — deletion of cloud subsystem.** After kast-web v2.0 cloud is proven:
    - Delete `kast/terraform/{aws,azure,gcp}/`.
    - Delete `kast/scripts/zap_provider_factory.py`, `zap_providers.py`, `zap_api_client.py`, `ssh_executor.py`, `terraform_manager.py`, `cleanup_orphaned_resources.py`, `diagnose_infrastructure.py`, `find_zap_url.py`, `monitor_zap.py`.
    - Delete `kast/config/zap_cloud_config.yaml`, `kast/config/nginx/`.
    - In `kast/plugins/zap_plugin.py`: remove `execution_mode == 'cloud'` branch from config schema, `_load_config`, `is_available`, and `run`. The `_warn_cloud_mode_deprecated` helper is removed too.
    - In `kast/plugins/zap_plugin.py` config schema, drop `cloud` from the enum (`local | remote | auto` only).
    - Delete the cloud-related tests if any remain.
    - The `cloud` ZAP profile (if any) goes away.
    - Remove the deprecation-warning test from D9.

### kast-web (companion repo, branch `refactor/v2.0`)

- **D1–D3 — port the cloud runtime from kast to kast-web** (re-architected, not lift-and-shift).
- **D4 — Celery tasks for cloud lifecycle.**
- **D5 — Celery Beat for orphan cleanup.**
- **D6 — admin UI for cloud credentials.** (Mostly already exists at `/admin/zap` — needs adaptation.)
- **D7 — admin UI for active cloud scans + orphans.**
- **D8 — `/api/cloud/*` and `/admin/cloud/*` routes.**
- **D11 — migration guide for v2.x kast cloud users.**

## Detailed kast-web design

### File-by-file plan for `kast-web/app/cloud/`

```
kast-web/app/cloud/
├── __init__.py
├── orchestrator.py         # Provision / scan / teardown lifecycle (ported from kast.scripts.zap_provider_factory + zap_providers)
├── providers/
│   ├── __init__.py
│   ├── base.py             # CloudProvider ABC (provision, get_zap_endpoint, teardown, get_status)
│   ├── aws.py              # ported from kast.scripts.zap_providers AWS bits
│   ├── azure.py            # ported from kast.scripts.zap_providers Azure bits
│   └── gcp.py              # ported from kast.scripts.zap_providers GCP bits
├── terraform_manager.py    # ported from kast.scripts.terraform_manager
├── ssh_executor.py         # ported from kast.scripts.ssh_executor
├── zap_api_client.py       # ported from kast.scripts.zap_api_client
├── cleanup.py              # orphan detection + cleanup, scheduled by Celery Beat
├── diagnostics.py          # ported from kast.scripts.diagnose_infrastructure (admin troubleshooting)
├── routes.py               # /api/cloud/* and /admin/cloud/* (Flask blueprint)
└── terraform/              # ported from kast/terraform/
    ├── aws/
    ├── azure/
    └── gcp/
```

The blueprint is registered in `kast-web/app/__init__.py` alongside `zap_admin`, `scans`, `api`, etc.

### Adaptations from kast → kast-web

Each ported file needs these adaptations:

| File | Adaptation |
| ---- | ---------- |
| `terraform_manager.py` | Replace any `kast.config` imports. State files now live under `kast_results_root/cloud_state/<scan_id>/`, owned by the kast-web user (not kast CLI). Logger goes through Flask's `current_app.logger`. |
| `ssh_executor.py` | Same logger swap. Key paths come from `cloud_credentials` model fields (decrypted) rather than `~/.ssh/`. |
| `zap_api_client.py` | Identical logic; only logger swap. |
| `zap_providers.py` (split into `providers/{aws,azure,gcp}.py`) | The provider classes return `{zap_url, api_key, instance_id, terraform_state_path}` to the orchestrator instead of opaque "instance_info" dicts that flow back to kast. |
| `zap_provider_factory.py` (becomes `orchestrator.py`) | The factory pattern goes away — kast-web has the provider type explicit in the cloud config. The orchestrator exposes three top-level entry points: `provision_for_scan(scan_id)`, `teardown_for_scan(scan_id)`, `cleanup_orphans()`. |
| `cleanup_orphaned_resources.py` (becomes `cleanup.py`) | Hooks into Celery Beat schedule. Detects orphans by comparing `cloud_scans` table state vs. live cloud resources. |
| Terraform configs (`terraform/{aws,azure,gcp}/`) | Templates unchanged. Variable injection now happens via `terraform_manager.py` writing tfvars from the ScanCloudConfig. |

### New database tables

Add via `utils/migrate_cloud_v2.py`:

```python
class CloudCredential(db.Model):
    """Per-org cloud provider credentials, encrypted at rest.

    Replaces the cloud_config_encrypted blob currently in ZapConfiguration:
    we want to manage credentials separately from ZAP plan choice.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))                # display name
    provider = db.Column(db.String(20))             # aws | azure | gcp
    credentials_encrypted = db.Column(db.Text)      # encrypt_json({access_key, secret, ...})
    region = db.Column(db.String(64))               # default region
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


class CloudScan(db.Model):
    """One row per cloud-provisioned ZAP scan.

    Tracks the infrastructure lifecycle separately from the Scan record.
    """
    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey('scan.id'), unique=True)
    cloud_credential_id = db.Column(db.Integer, db.ForeignKey('cloud_credential.id'))
    provider = db.Column(db.String(20))
    instance_id = db.Column(db.String(120))         # cloud-side identifier
    zap_url = db.Column(db.String(255))             # provisioned ZAP endpoint
    zap_api_key_encrypted = db.Column(db.Text)
    terraform_state_path = db.Column(db.String(500))
    status = db.Column(db.String(20))               # provisioning | scanning | tearing_down | torn_down | failed | orphaned
    provisioned_at = db.Column(db.DateTime)
    torn_down_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)


class CloudOrphan(db.Model):
    """Resources we detected but couldn't reconcile to a CloudScan."""
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(20))
    resource_id = db.Column(db.String(255))
    resource_type = db.Column(db.String(64))        # ec2_instance | rg | vm | etc.
    detected_at = db.Column(db.DateTime)
    cleanup_scheduled_for = db.Column(db.DateTime)
    cleanup_attempts = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20))               # detected | scheduled | cleaned | manual_review
```

Migration script follows kast-web's pattern: `PRAGMA table_info` checks, `ALTER TABLE` adds, idempotent re-runs. See `utils/migrate_zap_feature.py` as reference.

### Celery tasks

Add to `kast-web/app/tasks.py`:

```python
@celery.task(bind=True)
def cloud_provision_task(self, scan_id):
    """Provision cloud infrastructure for a scan, then chain to the scan task.

    Replaces the cloud-mode env-var injection in execute_scan_task. Runs as
    its own task so progress is visible and provisioning failures don't
    waste a scan slot.
    """

@celery.task(bind=True)
def cloud_teardown_task(self, cloud_scan_id):
    """Idempotent teardown. Always run after the scan completes (success or fail)."""

@celery.task
def cloud_orphan_cleanup_task():
    """Scheduled by Celery Beat. Walk cloud_scans for stuck resources, detect orphans, schedule cleanup."""
```

The scan flow becomes:

```python
# In execute_scan_task, when ZapConfiguration says cloud:
provision_result = cloud_provision_task.apply_async(args=[scan.id]).get(timeout=600)
zap_url, zap_api_key = provision_result["zap_url"], provision_result["zap_api_key"]
# build kast cmd with --set zap.execution_mode=remote and --set zap.remote.url=...
subprocess.run(cmd, ...)
cloud_teardown_task.delay(provision_result["cloud_scan_id"])
```

### Celery Beat schedule

In `kast-web/celery_worker.py`:

```python
celery.conf.beat_schedule = {
    'cloud-orphan-cleanup': {
        'task': 'app.tasks.cloud_orphan_cleanup_task',
        'schedule': 900.0,  # every 15 minutes
    },
}
```

### Admin UI surfaces

The existing `/admin/zap` UI manages a single ZapConfiguration with cloud_config_encrypted. v2.0 splits this:

- **`/admin/cloud/credentials`** — new. CRUD for CloudCredential rows. Each shows `provider | name | region | last used`. Encrypted fields display as `••••••••` after first save.
- **`/admin/cloud/scans`** — new. Live view of CloudScan rows (status, age, cost-so-far if computable, scan link).
- **`/admin/cloud/orphans`** — new. CloudOrphan rows + manual-cleanup actions.
- **`/admin/zap`** — updated. ZAP-configuration form drops the cloud_config blob; instead it references a CloudCredential by ID.

All four reuse the existing admin Bootstrap 5 pattern (`base.html` + `@admin_required` decorator + WTForms + AuditLog logging).

### API routes (`/api/cloud/*`)

- `GET /api/cloud/scans/<id>/status` — JSON status of a CloudScan (frontend polls this during cloud scans, same way it polls `/api/scans/<id>/status` today).
- `GET /api/cloud/orphans` — admin-only, JSON list.
- `POST /api/cloud/orphans/<id>/cleanup` — admin-only, manually trigger orphan teardown.

### kast CLI integration changes

The kast-web `execute_scan_task` (in `app/tasks.py`) replaces the `--set zap.execution_mode=cloud` branch with:

1. Lookup ZapConfiguration: if `execution_mode == 'cloud'`, branch to provisioning.
2. Call `cloud_provision_task` synchronously (block until provisioned).
3. Build the kast command with `--set zap.execution_mode=remote` and the ZAP endpoint + API key from the provision result.
4. Run the kast subprocess.
5. Schedule `cloud_teardown_task` (fires regardless of scan outcome).

The kast CLI no longer sees `cloud` mode at all. After D10, kast.zap_plugin's config schema drops `cloud` from the enum.

## Migration sequence

This order respects the runtime dependency: kast-web v2.0 cloud must work before kast cloud mode is removed.

1. **kast-web `refactor/v2.0` branch.** Confirm it exists and is current. Set up `kast-web/CLAUDE.md` (Phase D briefing) so a fresh session has context.
2. **D1–D3 (port code):** create `app/cloud/` skeleton, port `terraform_manager`, `ssh_executor`, `zap_api_client`, providers, terraform configs. Tests pass.
3. **DB migration:** `utils/migrate_cloud_v2.py` adds the three new tables. Backfill any existing ZapConfiguration cloud_configs into CloudCredential rows.
4. **D4 (Celery tasks):** `cloud_provision_task`, `cloud_teardown_task`. Wired but not yet invoked from `execute_scan_task`.
5. **D5 (Celery Beat):** `cloud_orphan_cleanup_task` scheduled.
6. **D6 (admin UI: credentials):** new `/admin/cloud/credentials` blueprint, CRUD against CloudCredential.
7. **D7 (admin UI: scans + orphans):** `/admin/cloud/scans` and `/admin/cloud/orphans`.
8. **D8 (API routes):** `/api/cloud/*` for status polling and admin actions.
9. **`execute_scan_task` cutover:** replace cloud-mode env-var injection with the provision-then-remote flow described above. This is the moment cloud actually runs through the new path.
10. **End-to-end smoke test:** real cloud scan against a test target on at least one provider (recommend AWS first; cheapest spot pricing). Validates provisioning, scan, teardown, orphan detection.
11. **D11 (migration guide):** `kast-web/docs/MIGRATION_FROM_KAST_CLOUD.md`. For users on kast 2.x cloud mode: how to move to kast-web 2.0 cloud.
12. **kast D10 (delete cloud code):** in this repo, on `refactor/v3.0`, delete the cloud-subsystem files and tests.
13. **Coordinated release:** kast 3.0 + kast-web 2.0 tagged simultaneously.

## Out of scope

- **Multi-cloud-per-org pricing comparisons.** Useful long-term; not v3.
- **Self-service org-level credential rotation flows.** Admin UI only writes; users don't see creds.
- **VPC peering for private targets.** v3 cloud ZAP runs against publicly reachable targets only. The audit/ideation deferred private-target scanning to v3.1+.
- **Auto-tuning of cloud spot pricing.** v2.0 keeps the existing `spot_max_price` config; auto-bidding is future work.

## Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Terraform state corruption when kast-web user differs from kast CLI user | Med | High | New state-file path under `kast_results_root/cloud_state/`. Migration script copies any existing `~/.kast/terraform_state/` content into the new location. |
| Existing cloud customers break during cutover | Low (small user base) | High | D9 deprecation warning gives advance notice. D10 only happens after kast-web v2.0 ships. Customer migration guide details the upgrade path. |
| Celery Beat missing orphan cleanup runs | Med | Medium (cost) | 15-min schedule is conservative. Manual cleanup endpoint at `/api/cloud/orphans/<id>/cleanup` lets admins force a run. |
| Encrypted credential migration loses data | Low | High | Migration script logs what it touches; original ZapConfiguration rows are kept until manual deletion (no destructive overwrite). |
| Provisioning failures leave half-built infrastructure | Med | High | `cloud_teardown_task` runs even if provisioning fails partway. Cleanup task catches anything missed. |

## Frozen contract preservation

The kast↔kast-web contract documented in `kast/docs/web-integration.md` does **not** change in Phase D:

- kast still writes `*_processed.json` files atomically.
- kast still emits `kast_info.json`, `zap_scan_progress.json`, `missing_issue_ids.json`.
- kast-web still spawns kast via subprocess with the same argv shape.
- The only kast-side surface change is removing `cloud` from the `zap.execution_mode` enum (D10). That breaks no automation: nothing outside kast or kast-web invokes `--set zap.execution_mode=cloud` directly.

Phase D is purely additive on the kast-web side until D10.
