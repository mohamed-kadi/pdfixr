# PDF Form SaaS Starter (Scalable)

Multi-tenant SaaS starter for PDF processing operations across viewers (Preview, Chrome, Acrobat).

## What It Supports

- Multi-operation PDF processing:
  - `font_fix` (serif-safe AcroForm normalization: `/DA`, `/DR`, `/XFA` cleanup)
  - `compress` (stream/object recompression for smaller files)
  - Compression result includes input/output size and reduction %
- Async background jobs
- Storage abstraction for local disk and S3-compatible object storage
- Signed download URLs for object storage mode
- Multi-tenant workspaces with user accounts (and legacy access codes)
- Monthly per-workspace usage limits
- Atomic quota reservation to prevent race-condition overages
- Billing-event driven plan upgrades/downgrades
- Quota reset scheduler (monthly period rows + retention cleanup)
- Local queue mode (ThreadPool) or distributed queue mode (Celery + Redis)
- Automatic retry scheduling with exponential backoff for transient job failures
- SQLite for local dev, Postgres-ready for production
- Separated Angular frontend (`frontend/`) for client and admin portals
- Admin audit/billing views separate from client upload page
- Job result notification emails (completed/failed) to active client users

## Client-Friendly Terms

- Client Account: email + password login linked to a workspace.
- Admin Account: email + password login for internal management.
- Token Session: after sign-in, frontend uses bearer token auth.
- Access/Admin codes: still supported for legacy/API workflows.
- Client Sign In: `http://localhost:4200/sign-in`
- Forgot Password: `http://localhost:4200/forgot-password`
- Reset Password: `http://localhost:4200/reset-password?token=<token>`
- Client Page: `http://localhost:4200/` (upload/download only, protected by sign-in)
- Admin Sign In: `http://localhost:4200/admin/sign-in`
- Admin Pages:
  - `http://localhost:4200/admin/workspaces`
  - `http://localhost:4200/admin/users`
  - `http://localhost:4200/admin/billing`
  - `http://localhost:4200/admin/audit`

## Core Structure

- `backend/app/services/pdf_processor.py`: core PDF normalization logic
- `backend/app/services/jobs.py`: job execution function
- `backend/app/services/plans.py`: plan limits + period helpers
- `backend/app/services/storage.py`: local/S3 storage backend abstraction
- `backend/app/queueing.py`: local or Celery dispatcher
- `backend/app/worker.py`: Celery worker task
- `backend/app/scheduler.py`: quota reset/background maintenance
- `backend/app/models.py`: `Workspace`, `Job`, `WorkspaceUsage`, `BillingEvent`
- `backend/app/api/routes.py`: API endpoints
- `frontend/`: Angular frontend app
  - `src/app/pages/client-portal`: client-facing upload/download UI
  - `src/app/pages/admin-console`: admin layout shell (nav + section routing)
  - `src/app/pages/admin-workspaces`: workspace creation and plan management
  - `src/app/pages/admin-users`: user creation, access management, password reset
  - `src/app/pages/admin-billing`: billing events view
  - `src/app/pages/admin-audit`: global audit logs view
  - `src/app/core/api.service.ts`: typed API client
- `fix_pdf_fonts.py`: CLI processor
- `verify_pdf_result.py`: acceptance validator

## Setup

### Backend

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

### Frontend (Angular)

```bash
cd frontend
PATH=/opt/homebrew/bin:$PATH npm install
```

Admin UI can be optionally host-gated in the frontend (for example, only allow `/admin/*` on `admin.yourdomain.com`).  
See `frontend/README.md` section `Admin Host Gating (Optional)`.

## Team Workflow (GitHub + Branches + CI)

- CI pipeline is defined in `.github/workflows/ci.yml`.
- Branch workflow guide is in `docs/DEVELOPMENT_WORKFLOW.md`.
- Recommended long-lived branches:
  - `main` (production)
  - `develop` (integration)
  - feature branches: `feature/<topic>`
  - fix branches: `fix/<topic>`

Initialize repo and push:

```bash
git init -b main
git add .
git commit -m "chore: initialize project"
git branch develop
git remote add origin <your-github-repo-url>
git push -u origin main
git push -u origin develop
```

## Local Dev Run

### 1) Start backend API (port 8000)

```bash
python run_api.py
```

### 2) Start frontend app (port 4200)

```bash
cd frontend
PATH=/opt/homebrew/bin:$PATH npm start
```

Open:
- Client sign in: `http://localhost:4200/sign-in`
- Forgot password: `http://localhost:4200/forgot-password`
- Reset password: `http://localhost:4200/reset-password`
- Client portal: `http://localhost:4200/`
- Admin sign in: `http://localhost:4200/admin/sign-in`
- Admin workspaces: `http://localhost:4200/admin/workspaces`
- Admin users: `http://localhost:4200/admin/users`
- Admin billing: `http://localhost:4200/admin/billing`
- Admin audit: `http://localhost:4200/admin/audit`
- API docs: `http://localhost:8000/docs`

Default dev accounts:
- Client: `client@local.dev` / `Client123!!`
- Admin: `admin@local.dev` / `Admin123!!`

Legacy codes (still supported):
- Access code: `dev-local-api-key`
- Admin code: `dev-admin-key`

## Client Handoff (Copy/Paste)

Use this when sharing with non-technical clients:

```text
Your PDF fixing portal is ready.

1) Open: <your-frontend-signin-url>
2) Enter your email + password
3) Upload your PDF
4) Wait for processing
5) Download the processed PDF

If upload fails, send me a screenshot and I will check it.
```

For a full plain-language handoff file, see `CLIENT_HANDOFF.md`.

## How To See Features Quickly

1. Start API:

```bash
python run_api.py
```

2. Start Angular frontend:

```bash
cd frontend
PATH=/opt/homebrew/bin:$PATH npm start
```

3. Open client UI at `http://localhost:4200/sign-in`:
- Sign in with `client@local.dev` / `Client123!!`.
- If needed, run `/forgot-password` then `/reset-password` to recover account access.
- By default, reset emails are written to `backend/storage/mail_outbox/` (file delivery mode).
- Job status notifications are also written there in `file` mode.
- Upload `input.pdf` and choose an operation (`font_fix` or `compress`).
- Watch status move `queued -> processing -> completed`.
- Download the processed PDF.
- This page is client-facing (upload, status, download only).

4. Open Admin UI at `http://localhost:4200/admin/sign-in`:
- Sign in with `admin@local.dev` / `Admin123!!`.
- Use separated admin routes for focused debugging:
  - `/admin/workspaces`: create workspaces + edit plan/limits/billing state
  - `/admin/users`: create users + update role/workspace/status + reset passwords
  - `/admin/billing`: inspect billing events
  - `/admin/audit`: inspect global audit logs

5. Trigger quota rejection (`429`) with a small-limit workspace:

(Using legacy admin key for quick CLI example.)

```bash
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: dev-admin-key" \
  -d '{"name":"QA Limit 1","plan_name":"starter","monthly_job_limit":1}'
```

Use returned `access_code` in the UI, upload twice, and confirm:
- second upload fails with quota message
- Admin audit logs show `job.rejected_quota`

6. Trigger billing lock (`402`) and recovery:
- Send `invoice.payment_failed` webhook for that workspace
- confirm uploads are blocked (`402`) and logs show `job.rejected_billing`
- send `customer.subscription.updated` (`status=active`) and confirm uploads work again

7. Open API docs:
- `http://localhost:8000/docs` for all routes and payloads

8. Run integration tests for proof:

```bash
./venv/bin/python -m pytest tests -q
```

## Distributed Run (Postgres + Redis + Celery)

```bash
docker compose up --build
```

This starts:
- API server
- Celery worker
- Redis broker
- Postgres DB
- Angular frontend (`http://localhost:4200`)

If you want Celery in local non-Docker mode:

```bash
export PDF_SAAS_QUEUE_BACKEND=celery
export PDF_SAAS_CELERY_BROKER_URL=redis://localhost:6379/0
export PDF_SAAS_CELERY_RESULT_BACKEND=redis://localhost:6379/1
python run_api.py
```

In another terminal:

```bash
source venv/bin/activate
python run_worker.py
```

## API Endpoints

### Auth/Workspace

- `POST /api/v1/auth/login` (email + password -> bearer token)
- `GET /api/v1/auth/me` (current authenticated user)
- `POST /api/v1/auth/password-reset/request` (request reset token)
- `POST /api/v1/auth/password-reset/confirm` (set new password with reset token)
- `GET /api/v1/me/workspace` (requires workspace context)
- `POST /api/v1/workspaces` (admin only)
- `GET /api/v1/workspaces` (admin only)
- `PATCH /api/v1/workspaces/{workspace_id}/plan` (admin only)
- `GET /api/v1/users` (admin only)
- `POST /api/v1/users` (admin only; create admin/client users)
- `PATCH /api/v1/users/{user_id}` (admin only; update role/workspace/active)
- `POST /api/v1/users/{user_id}/reset-password` (admin only)
- `GET /api/v1/auth/security/backend` (admin only; reports active auth security backend)
- `POST /api/v1/billing/webhook/stripe` (Stripe-Signature required)
- `GET /api/v1/billing/events` (admin only)
- `GET /api/v1/me/audit/logs`
- `GET /api/v1/audit/logs` (admin only)

Auth hardening:
- `POST /auth/login`, `POST /auth/password-reset/request`, and `POST /auth/password-reset/confirm` can return `429` with `Retry-After` when throttled/locked.
- Redis-backed shared throttling/lockouts can be enabled with `PDF_SAAS_AUTH_SECURITY_BACKEND=redis`.

### Jobs

- `POST /api/v1/jobs` (multipart: `file`, optional `job_type`, optional `job_options`)
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/download`
- `GET /api/v1/health`

Preferred header:

```text
Authorization: Bearer <token>
```

Legacy headers are still accepted:

```text
X-API-Key: <access_code>
X-Admin-Key: <admin_code>
```

Legacy auth login endpoints are also still available:
- `POST /api/v1/auth/client/login`
- `POST /api/v1/auth/admin/login`

## CLI Usage

```bash
python fix_pdf_fonts.py -i input.pdf -o output.pdf
```

Options:
- `--font-resource /Times`
- `--base-font /Times-Roman`
- `--font-size 12`

## Client Acceptance Verification

1. Process:

```bash
python fix_pdf_fonts.py -i input.pdf -o output.pdf
python verify_pdf_result.py output.pdf
```

2. Open `output.pdf` in Preview, type `Test`, save as `output_preview_saved.pdf`.
3. Validate:

```bash
python verify_pdf_result.py output_preview_saved.pdf --expect-text Test
```

4. Open `output_preview_saved.pdf` in Chrome and visually confirm serif text.

## Environment Variables

### Core

- `PDF_SAAS_STORAGE_ROOT` (default: `backend/storage`)
- `PDF_SAAS_STORAGE_BACKEND` = `local` or `s3` (default: `local`)
- `PDF_SAAS_STORAGE_SIGNED_URL_TTL_SECONDS` (default: `900`)
- `PDF_SAAS_STORAGE_S3_BUCKET` (required for `s3` backend)
- `PDF_SAAS_STORAGE_S3_REGION` (optional)
- `PDF_SAAS_STORAGE_S3_ENDPOINT_URL` (optional; use for MinIO/R2/custom S3 endpoints)
- `PDF_SAAS_STORAGE_S3_ACCESS_KEY_ID` (optional; provider dependent)
- `PDF_SAAS_STORAGE_S3_SECRET_ACCESS_KEY` (optional; provider dependent)
- `PDF_SAAS_STORAGE_S3_USE_SSL` (default: `true`)
- `PDF_SAAS_DATABASE_URL` (default: SQLite)
- `PDF_SAAS_DB_AUTO_INIT` (default: `true`; set `false` when using Alembic-managed schema)
- `PDF_SAAS_MAX_UPLOAD_MB` (default: `25`)
- `PDF_SAAS_ALLOWED_EXTENSIONS` (default: `.pdf`)
- `PDF_SAAS_API_PREFIX` (default: `/api/v1`)
- `PDF_SAAS_CORS_ORIGINS` (default: `http://localhost:4200,http://127.0.0.1:4200`)

### Queue

- `PDF_SAAS_QUEUE_BACKEND` = `local` or `celery` (default: `local`)
- `PDF_SAAS_WORKER_CONCURRENCY` (local mode, default: `4`)
- `PDF_SAAS_CELERY_BROKER_URL` (default: `redis://localhost:6379/0`)
- `PDF_SAAS_CELERY_RESULT_BACKEND` (default: `redis://localhost:6379/1`)
- `PDF_SAAS_JOB_MAX_ATTEMPTS` (default: `3`)
- `PDF_SAAS_JOB_RETRY_BASE_DELAY_SECONDS` (default: `5`)
- `PDF_SAAS_RETRY_SCHEDULER_INTERVAL_SECONDS` (default: `5`)
- `PDF_SAAS_RETRY_SCHEDULER_BATCH_SIZE` (default: `20`)

### Auth / Tenancy / Limits

- `PDF_SAAS_REQUIRE_API_KEY` (default: `false`)
- `PDF_SAAS_ADMIN_API_KEY` (default: `dev-admin-key`)
- `PDF_SAAS_AUTH_TOKEN_SECRET` (default: admin key value)
- `PDF_SAAS_AUTH_TOKEN_TTL_SECONDS` (default: `43200` = 12h)
- `PDF_SAAS_PASSWORD_RESET_TOKEN_TTL_SECONDS` (default: `1800` = 30m)
- `PDF_SAAS_PASSWORD_RESET_RETURN_TOKEN` (default: `false`; set `true` only for local/dev testing)
- `PDF_SAAS_PASSWORD_RESET_UI_BASE_URL` (default: `http://localhost:4200`)
- `PDF_SAAS_EMAIL_DELIVERY_MODE` = `file` or `smtp` (default: `file`)
- `PDF_SAAS_EMAIL_OUTBOX_DIR` (default: `backend/storage/mail_outbox`)
- `PDF_SAAS_SMTP_HOST` (required for `smtp` mode)
- `PDF_SAAS_SMTP_PORT` (default: `587`)
- `PDF_SAAS_SMTP_USERNAME` / `PDF_SAAS_SMTP_PASSWORD`
- `PDF_SAAS_SMTP_USE_TLS` (default: `true`)
- `PDF_SAAS_SMTP_FROM_EMAIL` (default: `no-reply@local.dev`)
- `PDF_SAAS_AUTH_RATE_LIMIT_WINDOW_SECONDS` (default: `300`)
- `PDF_SAAS_AUTH_LOGIN_RATE_LIMIT_PER_IP` (default: `30`)
- `PDF_SAAS_AUTH_LOGIN_LOCKOUT_THRESHOLD` (default: `5`)
- `PDF_SAAS_AUTH_LOGIN_LOCKOUT_SECONDS` (default: `900`)
- `PDF_SAAS_AUTH_LOGIN_FAILURE_WINDOW_SECONDS` (default: `900`)
- `PDF_SAAS_AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT_PER_IP` (default: `10`)
- `PDF_SAAS_AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT_PER_EMAIL` (default: `3`)
- `PDF_SAAS_AUTH_PASSWORD_RESET_CONFIRM_RATE_LIMIT_PER_IP` (default: `12`)
- `PDF_SAAS_AUTH_SECURITY_BACKEND` = `auto`, `redis`, or `memory` (default: `auto`)
- `PDF_SAAS_AUTH_SECURITY_REDIS_URL` (default: empty, then falls back to `PDF_SAAS_CELERY_BROKER_URL`)
- `PDF_SAAS_AUTH_SECURITY_REDIS_KEY_NAMESPACE` (default: `pdfsaas:v1:auth`)
- `PDF_SAAS_DEFAULT_ADMIN_EMAIL` (default: `admin@local.dev`)
- `PDF_SAAS_DEFAULT_ADMIN_PASSWORD` (default: `Admin123!!`)
- `PDF_SAAS_DEFAULT_CLIENT_EMAIL` (default: `client@local.dev`)
- `PDF_SAAS_DEFAULT_CLIENT_PASSWORD` (default: `Client123!!`)
- `PDF_SAAS_DEFAULT_WORKSPACE_NAME` (default: `Default Workspace`)
- `PDF_SAAS_DEFAULT_WORKSPACE_API_KEY` (default: `dev-local-api-key`)
- `PDF_SAAS_DEFAULT_WORKSPACE_PLAN` (default: `starter`)
- `PDF_SAAS_DEFAULT_WORKSPACE_MONTHLY_LIMIT` (default: `200`)

### Billing / Scheduler

- `PDF_SAAS_BILLING_WEBHOOK_SECRET` (default: `dev-billing-secret`)
- `PDF_SAAS_STRIPE_WEBHOOK_TOLERANCE_SECONDS` (default: `300`)
- `PDF_SAAS_QUOTA_SCHEDULER_INTERVAL_SECONDS` (default: `3600`)
- `PDF_SAAS_USAGE_RETENTION_MONTHS` (default: `15`)

### Redis Auth Security (Recommended For Multi-Instance)

```bash
export PDF_SAAS_AUTH_SECURITY_BACKEND=redis
export PDF_SAAS_AUTH_SECURITY_REDIS_URL=redis://localhost:6379/2
export PDF_SAAS_AUTH_SECURITY_REDIS_KEY_NAMESPACE=pdfsaas:v1:auth
```

If `PDF_SAAS_AUTH_SECURITY_BACKEND=auto`, the app tries Redis first and falls back to in-memory limits when Redis is unavailable.

### S3 Storage Example (Shared File Layer)

```bash
export PDF_SAAS_STORAGE_BACKEND=s3
export PDF_SAAS_STORAGE_S3_BUCKET=pdf-form-saas
export PDF_SAAS_STORAGE_S3_REGION=us-east-1
export PDF_SAAS_STORAGE_S3_ENDPOINT_URL=
export PDF_SAAS_STORAGE_S3_ACCESS_KEY_ID=<key>
export PDF_SAAS_STORAGE_S3_SECRET_ACCESS_KEY=<secret>
export PDF_SAAS_STORAGE_SIGNED_URL_TTL_SECONDS=900
```

Notes:
- In `s3` mode, job input/output references are stored as `s3://...`.
- `/jobs/{id}/download` returns a temporary redirect to a signed URL.

## Create New Workspace (Admin)

```bash
# 1) Login admin user
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@local.dev","password":"Admin123!!"}' | python -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# 2) Create workspace
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -d '{"name":"Acme Inc","plan_name":"pro","monthly_job_limit":5000}'
```

Then create a client user for that workspace:

```bash
curl -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -d '{"email":"acme.user@example.com","password":"Client999!!","role":"client","workspace_id":"<workspace_id>","is_active":true}'
```

## Simulate Billing Webhook (Plan Update)

Generate a Stripe-style signature first:

```bash
BODY='{
  "provider_event_id":"evt_12345",
  "event_type":"customer.subscription.updated",
  "workspace_id":"<workspace_id>",
  "plan_name":"business",
  "monthly_job_limit":25000,
  "billing_status":"active",
  "stripe_customer_id":"cus_123",
  "stripe_subscription_id":"sub_123"
}'

SIG=$(python - <<'PY'
import hmac,hashlib,time,os
body=os.environ["BODY"]
secret="dev-billing-secret"
t=str(int(time.time()))
signed=f"{t}.{body}".encode()
digest=hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
print(f"t={t},v1={digest}")
PY
)
```

Then call webhook:

```bash
curl -X POST http://localhost:8000/api/v1/billing/webhook/stripe \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: ${SIG}" \
  -d "${BODY}"
```

## Alembic Migrations

For production, prefer explicit migrations instead of implicit auto-create:

```bash
source venv/bin/activate
alembic upgrade head
```

Create a new migration revision:

```bash
alembic revision -m "describe change"
```
