# Data model

Schema of the harvested snapshot (`data/` by default). Read this when the markdown
digest is not precise enough and you need to query the JSON directly.

All identifiers below are illustrative. `courseId` and `contentId` come from your own
institution's Blackboard instance.

## `index.json`

```jsonc
{
  "harvestedAt": "2026-09-12T12:44:49.584Z",   // ISO 8601, UTC
  "origin": "https://ntulearn.ntu.edu.sg",
  "user": { "id": "_0000000_1", "userName": "your-ntu-username", "name": { "given": "...", "family": "..." } },
  "courseCount": 8,
  "courses": [
    {
      "courseId": "_0000000_1",       // Blackboard course id — the join key everywhere
      "displayName": "26S1-XX1234-EXAMPLE COURSE",
      "term": "26S1",
      "ultraStatus": "Ultra",         // "Ultra" | "Original" | null
      "accessible": true,             // false => enrolment inactive, no content read
      "inaccessibleReason": null,     // server message when accessible is false
      "contentItems": 39,
      "assessments": 2,
      "announcements": 3,
      "digest": "digest/_0000000_1.md",
      "url": "https://ntulearn.ntu.edu.sg/ultra/courses/_0000000_1/outline"
    }
  ]
}
```

## `courses/<courseId>.json`

One record per course.

```jsonc
{
  "courseId": "_0000000_1",
  "displayName": "26S1-XX1234-EXAMPLE COURSE",
  "term": "26S1",
  "ultraStatus": "Ultra",
  "url": "https://ntulearn.ntu.edu.sg/ultra/courses/_0000000_1/outline",
  "harvestedAt": "2026-09-12T12:44:49.584Z",

  "access": { "accessible": true, "reason": null },

  // Every content item, flattened depth-first in outline order.
  "contentTree": [
    {
      "contentId": "_0000000_1",     // used in the UI deep link
      "courseId": "_0000000_1",
      "title": "Unit 1 Graded Quiz",
      "handler": "resource/x-bb-asmt-test-link",

      // Position in the hierarchy.
      "depth": 1,
      "breadcrumb": ["Unit 1: Foundations"],
      "modulePath": "Unit 1: Foundations",

      // Instructor-written text. This is the exam scope for an assessment.
      "description": "This is a timed quiz comprising 5 MCQs. ...",

      "dueDate": null,               // ISO 8601 UTC; null => no due date
      "dueDateExceptionType": "Normal",
      "hasGradeColumn": true,
      "visibility": "VISIBLE",

      // Present only when handler is an assessment.
      "assessment": {
        "id": "_0000000_1",          // internal assessment id (not the content id)
        "type": "Test",
        "subtype": null,             // "Assignment" | "KnowledgeCheck" | null
        "deployedAssessmentType": "test",
        "title": "Unit 1 Graded Quiz",
        "instructions": null,
        "description": null,
        "questionCount": 5,
        "totalPoints": 5,
        "lastModified": "2026-05-22T06:34:07.209Z"
      },
      "attempts": {
        "attemptCount": -1,          // -1 => UNLIMITED
        "unlimited": true
      },
      "timeLimitMinutes": 5,         // VERIFIED in minutes. null => no limit set.
      "timerCompletion": "HARDSTOP", // HARDSTOP auto-submits | CONTINUAL
      "exceptions": [],              // per-student accommodations, if any
      "settings": {
        "isDueDateEnforced": false,
        "isPasswordRequired": false,
        "isSecureBrowserRequiredToTake": false,
        "isRandomizationOfQuestionsRequired": true,
        "isRandomizationOfAnswersRequired": "ALWAYS",  // "ALWAYS" | "NEVER"
        "isBacktrackingProhibited": false,
        "isCompletionForced": false,
        "isScoreShown": false,
        "isCorrectAnswerShown": false,
        "isFeedbackShown": false,
        "isLateAttemptCreationDisallowed": false
      },
      "grading": {
        "possible": 5.0,
        "category": "Test.name",
        "columnId": "_0000000_1",    // join key to gradebookColumns / myGrades
        "aggregationModel": "LAST",
        "isAttemptBased": true,
        "gradesReleased": true,
        "enforceDueDate": false,
        "scorable": true
      },

      // Only when the user has a grade record for this column.
      "myGrade": {
        "status": "GRADED",
        "effectiveScore": 4.0,
        "displayGrade": 80.0,        // percentage as shown in the UI
        "pointsPossible": 5.0
      },
      "myAttempts": {
        "used": 1,
        "attemptsLeft": -1,          // -1 => unlimited
        "lastAttemptDate": "2026-09-07T07:57:00.310Z"
      },

      "sources": {
        "ui": "https://ntulearn.ntu.edu.sg/ultra/courses/_0000000_1/assessment/_0000000_1/overview?courseId=_0000000_1",
        "api": "https://ntulearn.ntu.edu.sg/learn/api/v1/courses/_0000000_1/contents/_0000000_1?expand=..."
      }
    }
  ],

  // Authoritative due dates / points, including columns that are not content
  // (e.g. "Attendance", "Overall Grade").
  "gradebookColumns": [
    {
      "id": "_0000000_1",
      "name": "Unit 1 Graded Quiz",
      "contentId": "_0000000_1",
      "dueDate": null,
      "possible": 5,
      "category": "Test.name",
      "assessmentSubtype": null,
      "multipleAttempts": 0,
      "aggregationModel": "LAST",
      "gradesReleased": true
    }
  ],

  "myGrades": [
    { "columnId": "_0000000_1", "columnName": "Unit 1 Graded Quiz", "status": "GRADED",
      "score": null, "scorePossible": null, "text": null, "feedback": null }
  ],

  "announcements": [
    { "id": "_0000000_1", "title": "...", "body": "<p>…</p>",
      "created": "2026-08-12T02:06:21.006Z",
      "url": "https://ntulearn.ntu.edu.sg/ultra/courses/_0000000_1/announcements" }
  ]
}
```

## Field semantics that are easy to get wrong

| Field | Meaning |
|---|---|
| `timeLimitMinutes` | **Minutes**, not seconds. Verified against the rendered UI. |
| `attempts.attemptCount: -1` | **Unlimited** attempts, not "no attempts". |
| `attempts.attemptCount: 0` | Usually means the value was not configured; check the UI. |
| `myAttempts.attemptsLeft: -1` | Unlimited remaining. |
| `myAttempts.used` | Count of attempt records; the reliable "how many times have I done it". |
| `description` vs `assessment.description` | The **item-level** `description` is where scope is written. `assessment.description` / `assessment.instructions` are usually empty. |
| `dueDate: null` + `settings.isDueDateEnforced: false` | No due date at all. If `dueDate` is set but `isDueDateEnforced` is false, the date is advisory. |
| `grading.possible` | Points available. Percentage marks live in `myGrade.displayGrade`. |

## Source endpoints

The harvester reads two surfaces. Both are re-discoverable with `npm run discover` if a
Blackboard upgrade moves them.

| Purpose | Endpoint |
|---|---|
| Course list | `GET /learn/api/public/v1/users/{userId}/courses?expand=course` |
| Announcements | `GET /learn/api/public/v1/courses/{cid}/announcements` |
| Outline | `GET /learn/api/v1/courses/{cid}/contents/{itemId}/children?@view=Summary&expand=…` |
| Item detail (scope, question count) | `GET /learn/api/v1/courses/{cid}/contents/{contentId}?expand=…` |
| Gradebook columns | `GET /learn/api/v1/courses/{cid}/gradebook/columns?expand=…` |
| My grade for a column | `GET /learn/api/v1/courses/{cid}/gradebook/columns/{columnId}/grades?expand=attemptsLeft&userId={uid}` |
| My attempts | `GET /learn/api/v1/courses/{cid}/gradebook/columns/{columnId}/grades/{gradeId}/attempts` |
