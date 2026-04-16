# TAS App API Documentation

## Base Path

- `/tas/api/v1/`

## Authentication

- Most endpoints require JWT or session authentication.
- Admin-only endpoints require `IsAdminUser`.
- Learner endpoints require `IsAuthenticated` and enforce ownership where applicable.

---

## 1) Template Types - List / Create

- **Title**: Template Types
- **Endpoint**: `GET /tas/api/v1/template-types/`
- **Request Type**: `GET`
- **Query Params**:
  - `is_active` (optional): `true` or `false`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Essay",
      "slug": "essay",
      "description": "Essay template",
      "icon": "/media/tas/templates/icons/essay.png",
      "is_active": true
    }
  ]
}
```

- **Endpoint**: `POST /tas/api/v1/template-types/`
- **Request Type**: `POST`
- **Payload**:

```json
{
  "name": "Case Study",
  "slug": "case-study",
  "description": "Case study assignments",
  "is_active": true
}
```

- **Response Code**: `201 Created`
- **Response Example**:

```json
{
  "id": 3,
  "name": "Case Study",
  "slug": "case-study",
  "description": "Case study assignments",
  "icon": null,
  "is_active": true
}
```

---

## 2) Template Type - Detail / Update / Soft Delete

- **Title**: Template Type Detail
- **Endpoint**: `GET /tas/api/v1/template-types/{pk}/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 1,
  "name": "Essay",
  "slug": "essay",
  "description": "Essay template",
  "icon": null,
  "is_active": true
}
```

- **Endpoint**: `PATCH /tas/api/v1/template-types/{pk}/`
- **Request Type**: `PATCH`
- **Payload**:

```json
{
  "description": "Updated description",
  "is_active": true
}
```

- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 1,
  "name": "Essay",
  "slug": "essay",
  "description": "Updated description",
  "icon": null,
  "is_active": true
}
```

- **Endpoint**: `DELETE /tas/api/v1/template-types/{pk}/`
- **Request Type**: `DELETE`
- **Payload**: Not required
- **Response Code**: `204 No Content`
- **Response Example**:

```json
{
  "detail": "TemplateType has been deactivated (soft deleted)."
}
```

---

## 3) Templates - List / Create

- **Title**: Templates
- **Endpoint**: `GET /tas/api/v1/templates/`
- **Request Type**: `GET`
- **Query Params**:
  - `template_type` (optional): template type ID
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 10,
      "template_type": 1,
      "name": "Essay Basic",
      "description": "Basic essay layout",
      "image": "/media/tas/templates/images/essay.png",
      "image_width": 1080,
      "image_height": 1920,
      "thumbnail": "/media/tas/templates/thumbnails/essay-thumb.png",
      "fields": [],
      "field_positions": {},
      "is_public": false,
      "is_active": true
    }
  ]
}
```

- **Endpoint**: `POST /tas/api/v1/templates/`
- **Request Type**: `POST`
- **Payload**:

```json
{
  "template_type": 1,
  "name": "Essay Basic",
  "description": "Basic essay layout",
  "image_width": 1080,
  "image_height": 1920,
  "fields": [],
  "field_positions": {},
  "is_public": true,
  "is_active": true
}
```

- **Response Code**: `201 Created`
- **Response Example**:

```json
{
  "id": 10,
  "template_type": 1,
  "name": "Essay Basic",
  "description": "Basic essay layout",
  "image": null,
  "image_width": 1080,
  "image_height": 1920,
  "thumbnail": null,
  "fields": [],
  "field_positions": {},
  "is_public": true,
  "is_active": true
}
```

---

## 4) Template - Detail / Update / Soft Delete

- **Title**: Template Detail
- **Endpoint**: `GET /tas/api/v1/templates/{pk}/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 10,
  "template_type": 1,
  "name": "Essay Basic",
  "description": "Basic essay layout",
  "image": null,
  "image_width": 1080,
  "image_height": 1920,
  "thumbnail": null,
  "fields": [],
  "field_positions": {},
  "is_public": true,
  "is_active": true
}
```

- **Endpoint**: `PUT /tas/api/v1/templates/{pk}/`
- **Request Type**: `PUT`
- **Payload**:

```json
{
  "template_type": 1,
  "name": "Essay Revised",
  "description": "Revised template",
  "image_width": 1080,
  "image_height": 1920,
  "fields": [],
  "field_positions": {},
  "is_public": false,
  "is_active": true
}
```

- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 10,
  "template_type": 1,
  "name": "Essay Revised",
  "description": "Revised template",
  "image": null,
  "image_width": 1080,
  "image_height": 1920,
  "thumbnail": null,
  "fields": [],
  "field_positions": {},
  "is_public": false,
  "is_active": true
}
```

- **Endpoint**: `PATCH /tas/api/v1/templates/{pk}/`
- **Request Type**: `PATCH`
- **Payload**:

```json
{
  "name": "Essay Updated"
}
```

- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 10,
  "template_type": 1,
  "name": "Essay Updated",
  "description": "Revised template",
  "image": null,
  "image_width": 1080,
  "image_height": 1920,
  "thumbnail": null,
  "fields": [],
  "field_positions": {},
  "is_public": false,
  "is_active": true
}
```

- **Endpoint**: `DELETE /tas/api/v1/templates/{pk}/`
- **Request Type**: `DELETE`
- **Payload**: Not required
- **Response Code**: `204 No Content`
- **Response Example**:

```json
{
  "detail": "Template has been deactivated (soft deleted)."
}
```

---

## 5) Block Template Details

- **Title**: Template Block Details
- **Endpoint**: `GET /tas/api/v1/blocks/{usage_key}/templates/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "usage_key": "block-v1:Org+Course+Run+type@tas+block@unit1",
  "course_id": "course-v1:Org+Course+Run",
  "templates": {
    "template_block_id": "5",
    "sort_order": 0,
    "template": {
      "id": 10,
      "name": "Essay Basic",
      "template_type": {
        "slug": "essay",
        "name": "Essay"
      },
      "thumbnail_url": "https://example.com/media/.../thumb.png",
      "image_width": 1080,
      "image_height": 1920
    }
  }
}
```

---

## 6) Student Submission - Create or Update

- **Title**: Student Submission Create/Update
- **Endpoint**: `POST /tas/api/v1/student-submission/`
- **Request Type**: `POST`
- **Payload**:

```json
{
  "template_block_id": "5",
  "course_key": "course-v1:Org+Course+Run",
  "usage_key": "block-v1:Org+Course+Run+type@tas+block@unit1",
  "form_data": {
    "answer_1": "My answer"
  },
  "status": "draft"
}
```

- **Response Code**: `201 Created` (new) / `200 OK` (update)
- **Response Example**:

```json
{
  "id": 100,
  "template_block_id": "5",
  "student_id": "learner1",
  "course_id": "course-v1:Org+Course+Run",
  "usage_key": "block-v1:Org+Course+Run+type@tas+block@unit1",
  "form_data": {
    "answer_1": "My answer"
  },
  "status": "draft",
  "version_number": 1,
  "submitted_at": null,
  "pdf_url": "",
  "created_at": "2026-04-10T08:00:00Z",
  "updated_at": "2026-04-10T08:00:00Z"
}
```

---

## 7) Student Submission - Detail / Patch

- **Title**: Student Submission Detail
- **Endpoint**: `GET /tas/api/v1/student-submission/{pk}/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 100,
  "template_block_id": "5",
  "student_id": "learner1",
  "course_id": "course-v1:Org+Course+Run",
  "usage_key": "block-v1:Org+Course+Run+type@tas+block@unit1",
  "form_data": {
    "answer_1": "My answer"
  },
  "status": "draft",
  "version_number": 2,
  "submitted_at": null,
  "pdf_url": "",
  "created_at": "2026-04-10T08:00:00Z",
  "updated_at": "2026-04-10T09:00:00Z"
}
```

- **Endpoint**: `PATCH /tas/api/v1/student-submission/{pk}/`
- **Request Type**: `PATCH`
- **Payload**:

```json
{
  "form_data": {
    "answer_1": "Updated answer"
  }
}
```

- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 100,
  "template_block_id": "5",
  "student_id": "learner1",
  "course_id": "course-v1:Org+Course+Run",
  "usage_key": "block-v1:Org+Course+Run+type@tas+block@unit1",
  "form_data": {
    "answer_1": "Updated answer"
  },
  "status": "draft",
  "version_number": 3,
  "submitted_at": null,
  "pdf_url": "",
  "created_at": "2026-04-10T08:00:00Z",
  "updated_at": "2026-04-10T10:00:00Z"
}
```

---

## 8) Student Submission - Submit

- **Title**: Finalize Student Submission
- **Endpoint**: `POST /tas/api/v1/student-submission/{pk}/submit/`
- **Request Type**: `POST`
- **Payload**:

```json
{}
```

- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 100,
  "status": "submitted",
  "version_number": 4,
  "submitted_at": "2026-04-10T10:30:00Z",
  "pdf_url": null
}
```

---

## 9) Student Submission - PDF

- **Title**: Student Submission PDF
- **Endpoint**: `GET /tas/api/v1/student-submission/{pk}/pdf/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK` (available) / `202 Accepted` (generating)
- **Response Example (200)**:

```json
{
  "pdf_url": "https://example.com/media/tas/submissions/pdfs/submission-100.pdf"
}
```

- **Response Example (202)**:

```json
{
  "status": "generating",
  "pdf_url": null
}
```

---

## 10) Student Submission - Versions

- **Title**: Student Submission Version History
- **Endpoint**: `GET /tas/api/v1/student-submission/{pk}/versions/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "submission_id": "100",
  "versions": [
    {
      "version_number": 4,
      "form_data": {
        "answer_1": "Final answer"
      },
      "saved_at": "2026-04-10T10:30:00Z"
    },
    {
      "version_number": 3,
      "form_data": {
        "answer_1": "Updated answer"
      },
      "saved_at": "2026-04-10T10:00:00Z"
    }
  ]
}
```

---

## 11) Instructor - Block Submissions List

- **Title**: Learner Submissions for Block
- **Endpoint**: `GET /tas/api/v1/block/{usage_key}/submissions/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 100,
      "username": "learner1",
      "submission_date": "2026-04-10T10:30:00Z",
      "grade": "N/A",
      "grading_status": "submitted"
    }
  ]
}
```

---

## 12) Instructor - Submission Detail

- **Title**: Learner Submission Detail
- **Endpoint**: `GET /tas/api/v1/submissions/{pk}/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "id": 100,
  "username": "learner1",
  "course_key": "course-v1:Org+Course+Run",
  "usage_key": "block-v1:Org+Course+Run+type@tas+block@unit1",
  "submission_date": "2026-04-10T10:30:00Z",
  "status": "submitted",
  "version": 4,
  "form_data": {
    "answer_1": "Final answer"
  },
  "pdf": "/media/tas/submissions/pdfs/submission-100.pdf"
}
```

---

## 13) Instructor - Block Rubrics

- **Title**: Rubrics by Block
- **Endpoint**: `GET /tas/api/v1/block/{usage_key}/rubrics/`
- **Request Type**: `GET`
- **Payload**: Not required
- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "display_name": "Template Based Assignment",
  "instructions": "Read carefully and submit your best work.",
  "rubrics": [
    {
      "title": "Clarity",
      "max_score": 5
    }
  ]
}
```

---

## 14) Instructor - Submit Feedback

- **Title**: Instructor Feedback
- **Endpoint**: `POST /tas/api/v1/submissions/{pk}/feedback/`
- **Request Type**: `POST`
- **Payload**:

To Reject Submission:
```json
{
  "comment": "Improve structure.",
  "status": "rejected"
}
```
To Approve Submission:
```json
{
  "rubrics": [
    {
      "title": "Clarity",
      "score": 4
    }
  ],
  "comment": "Good effort. Improve structure.",
  "status": "approved"
}
```

- **Response Code**: `200 OK`
- **Response Example**:

```json
{
  "message": "Feedback saved successfully.",
  "created": true
}
```

---

## Common Error Responses

- `400 Bad Request` - Validation error or invalid operation.
- `401 Unauthorized` - Missing/invalid authentication.
- `403 Forbidden` - Authenticated but not permitted.
- `404 Not Found` - Resource does not exist.
- `409 Conflict` - Attempt to modify finalized submission.
