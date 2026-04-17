# Local Development Setup

Step-by-step guide to run `tas_integration` against a local Tutor Open edX instance.

## Prerequisites

- [Tutor](https://docs.tutor.overhang.io) v21+ installed
- Docker running
- LMS accessible at `http://local.openedx.io`

## Steps

### 1. Start Tutor

```bash
tutor local start -d
```

### 2. Mount the repo

Register a bind mount so your local code is live inside the container:

```bash
tutor mounts add "lms,lms-worker:/absolute/path/to/tas_integration:/openedx/tas_integration"
```

Then do a full stop/start (restart alone won't apply new mounts):

```bash
tutor local stop
tutor local start -d
```

Verify the mount:

```bash
docker exec tutor_local-lms-1 ls /openedx/tas_integration
```

### 3. Install the package

```bash
tutor local exec lms pip install -e /openedx/tas_integration
```

### 4. Run migrations

```bash
tutor local exec lms python /openedx/edx-platform/manage.py lms migrate tas_app
```

### 5. Restart LMS workers

```bash
tutor local restart lms
```

### 6. Verify

```bash
# Package installed
docker exec tutor_local-lms-1 pip show tas-integration

# Migration applied
tutor local exec lms python /openedx/edx-platform/manage.py lms showmigrations tas_app

# URLs reachable (expect 401, not 404)
curl -o /dev/null -w "%{http_code}" http://local.openedx.io/tas/api/v1/template-types/
```

## Making Code Changes

Since the package is installed in editable mode (`-e`), Python code changes are reflected immediately — no reinstall needed. However:

- **New migrations** → re-run `migrate tas_app`
- **New dependencies in `requirements/common.in`** → re-run `pip install -e /openedx/tas_integration`
- **New entry points in `setup.py`** → re-run `pip install -e /openedx/tas_integration` + restart LMS

## Getting a JWT Token

```bash
curl -s -X POST http://local.openedx.io/oauth2/access_token \
  -d "client_id=login-service-client-id" \
  -d "grant_type=password" \
  -d "username=admin" \
  -d "password=<your_password>" \
  -d "token_type=jwt"
```

Use the returned `access_token` as `Authorization: JWT <token>` in API requests.

## Example API Calls

**Create a template type:**

```bash
curl -X POST http://local.openedx.io/tas/api/v1/template-types/ \
  -H "Authorization: JWT <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Case Study", "slug": "case-study"}'
```

**List template types:**

```bash
curl http://local.openedx.io/tas/api/v1/template-types/ \
  -H "Authorization: JWT <token>"
```
