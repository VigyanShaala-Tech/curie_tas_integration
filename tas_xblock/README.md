# `tas_xblock` - TAS XBlock

`tas_xblock` is the learner/studio component for the TAS integration. It renders assignment instructions and template-driven workflows to learners, while giving course staff Studio controls to configure template type, template, and rubric metadata.

## Purpose

This XBlock bridges Studio authoring and runtime learner experience:

- Studio authors choose assignment template settings
- block configuration is persisted into `tas_app` data models
- learner view loads assignment context and frontend assets

## Key Behavior

- **Student view**
  - renders `static/html/tas.html`
  - loads `static/css/tas.css` and `static/js/tas.js`
  - exposes block settings such as display name, template selection, and instructions
- **Studio view**
  - renders `static/html/tas_edit.html`
  - loads edit assets
  - allows staff to configure display name, template type/template, instructions, and rubrics
- **Studio save handler**
  - stores configuration in XBlock fields
  - upserts a corresponding `TemplateBlock` record in `tas_app`

## Setup and Installation (Open edX)

### 1) Install plugin package

```bash
pip install -e /path/to/tas-integration
```

This package registers the XBlock entry point:

- `xblock.v1`: `tas = tas_xblock.tas:TASXBlock`

### 2) Restart LMS/CMS workers

Restart services so XBlock entry points are reloaded.

### 3) Enable advanced module in Studio

Add `tas` to the course **Advanced Module List**.

### 4) Add the block in a unit

In Studio unit editor:

- add the advanced component `tas`
- configure template type/template and instructions in the block editor
- publish course updates

## Dependencies and Runtime Requirements

- Requires `tas_app` to be installed and migrated, because Studio configuration reads/writes app models.
- Requires Open edX runtime services (i18n, user context, course access APIs).
- Requires static asset collection pipeline to include XBlock static files.

## Troubleshooting

- Block not visible in Studio:
  - verify `tas` is in Advanced Module List
  - verify service restart after install
- Studio save fails with "Template not found":
  - confirm template records exist in `tas_app`
- Learner/staff UI issues:
  - confirm static files are collected and served correctly
