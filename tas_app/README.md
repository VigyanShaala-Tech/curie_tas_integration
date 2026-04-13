# `tas_app` - TAS Django Application

`tas_app` is the Open edX pluggable Django app behind TAS (Templatized Assignment Service). It provides data models, admin integration, and REST APIs used by the TAS XBlock and staff tooling.

## Purpose

The app manages the full assignment data lifecycle:

- template categories (`TemplateType`)
- template definitions (`Template`)
- XBlock-to-template bindings (`TemplateBlock`)
- learner submissions with versioning (`Submission`, `SubmissionVersion`)
- instructor evaluation feedback (`InstructorFeedback`)

## Open edX Plugin Integration

The app is wired as a pluggable Open edX Django app via `TASIntegrationConfig`.

- LMS URL namespace is mounted under `/tas/`.
- Plugin settings hooks are available in:
  - `tas_app/settings/common.py`
  - `tas_app/settings/production.py`

## API Surface (high-level)

Base path: `/tas/api/v1/`

- Template types: list/detail CRUD-style endpoints
- Templates: list/detail CRUD-style endpoints
- Block template lookup: resolve selected template by XBlock `usage_key`
- Student submission flow:
  - create/update draft
  - submit/finalize
  - retrieve versions
  - fetch generated PDF URL
- Instructor flow:
  - list learner submissions per block
  - retrieve single learner submission
  - fetch block rubrics
  - submit feedback

Authentication uses session auth and JWT auth as configured in Open edX.

## Setup and Installation

### 1) Install package into Open edX environment

```bash
pip install -e /path/to/tas-integration
```

### 2) Apply migrations

```bash
python manage.py lms migrate tas_app
```

### 3) Restart services

Restart LMS and CMS so plugin discovery, URL registration, and model loading take effect.

### 4) Validate health

- Confirm `/tas/api/v1/template-types/` responds (auth required).
- Confirm admin/staff can create template types and templates.

## Operational Notes

- The app uses Open edX `CourseKeyField` and `UsageKeyField`, so data maps directly to Open edX course/unit identifiers.
- Submission uniqueness is enforced per learner per `(course_key, usage_key)`.
- Submissions can be drafted multiple times, versioned, and then finalized.
- Media storage must support:
  - template icons/images/thumbnails
  - learner submission PDFs

## Development Tips

- Run tests in `tas_app/tests/` while iterating on serializer/view/model behavior.
- Keep API contracts aligned with frontend/XBlock calls to avoid runtime mismatch.
