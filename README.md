# TAS Integration for Open edX

`tas-integration` is an Open edX plugin that combines:

- a pluggable Django app: `tas_app`
- an XBlock: `tas_xblock`

Together, they provide a template-driven assignment workflow where course teams configure assignment templates in Studio, learners submit responses (including PDF artifacts), and instructors review submissions with rubric-based feedback.

## Repository Structure

- `tas_app` - Open edX pluggable Django app (LMS/CMS plugin entry points, REST APIs, models, admin)
- `tas_xblock` - XBlock implementation rendered in LMS and editable in Studio
- `requirements/` - dependency input files
- `setup.py` - package metadata and plugin/XBlock entry points

## Purpose

This plugin is intended for assignment scenarios where a fixed visual or structured template is required (for example, worksheets, structured reports, or form-style submissions) while still fitting naturally into Open edX course authoring and learner workflows.

## How It Works

1. Administrators define template types and templates in the backend.
2. Course staff add a `tas` XBlock in Studio and select the required template plus instructions/rubrics.
3. Learners submit data through the block experience.
4. The app stores submission versions and optional PDF files.
5. Instructors fetch learner submissions and post rubric/comment feedback through secured APIs.

## Installation (Open edX)

### 1) Install package in your Open edX Python environment

Use editable mode during development:

```bash
pip install -e /path/to/tas-integration
```

Or install from a built wheel in production.

### 2) Ensure plugin loading via entry points

This package already exposes entry points for:

- `lms.djangoapp`: `tas_app`
- `cms.djangoapp`: `tas_app`
- `xblock.v1`: `tas`

After installation, restart LMS and CMS services so Open edX discovers the plugin.

### 3) Run migrations

Run Django migrations for LMS (and CMS if your deployment manages DB migrations from both):

```bash
python manage.py lms migrate tas_app
```

### 4) Enable the XBlock in Studio

In Studio advanced settings, add `tas` to **Advanced Module List** for the course (or globally using your platform policy if preferred).

### 5) Verify URL registration

The plugin registers LMS URLs under `/tas/` (for example `/tas/api/v1/...`).
Confirm the LMS service can resolve these endpoints after restart.

## Configuration Notes

- `tas_app` includes plugin settings hooks in `tas_app/settings/common.py` and `tas_app/settings/production.py`.
- Authentication for APIs supports session auth and JWT auth as implemented in app views.
- Uploaded media (template images/thumbnails and submission PDFs) must be supported by your Open edX media/storage configuration.

## Developer Setup

```bash
git clone <your-fork-or-repo-url>
cd tas-integration
pip install -e .
pip install -r requirements/common.in
```

Then install into your Open edX runtime and run migrations as described above.

## Module Documentation

- App-level documentation: `tas_app/README.md`
- XBlock-level documentation: `tas_xblock/README.md`