---
name: ntulearn
description: >-
  Answers questions about the user's NTULearn (Blackboard Learn Ultra) courses from a
  local harvested snapshot — course content, outlines, quizzes and tests (time limit,
  attempts allowed and used, due dates, exam scope), assignments, announcements, and
  the user's own marks. Every answer cites the course page and API URL it came from.
  Use whenever the user asks about their NTU modules, course content, quizzes, tests,
  assignments, deadlines, or grades.
whenToUse: >-
  Trigger on any question about the user's NTU courses or coursework: "quiz 时间/次数/考试范围",
  "when is my assignment due", "what's in week 5 of XX1234", "what did the announcement
  say", "how many attempts do I have left", "what's my mark for X", "which courses am I in".
user-invocable: true
metadata:
  version: "1.0.0"
---

# NTULearn content assistant

Answers questions about the user's NTULearn courses from a **local snapshot** of their
Blackboard Learn Ultra account.

The snapshot is produced by the harvester in this repository and is far richer than what
the web pages show at a glance: assessment configuration, attempts used, and the
exam-scope text instructors write into each assessment.

## Prerequisite

A snapshot must exist. If the paths below are missing, the harvester has not been run —
tell the user to follow the instructions in `harvester/README.md`, which requires a
one-time interactive sign-in (NTU enforces MFA, so no script can do it for them).

## Where the data is

Default layout, relative to the user's workspace root:

| Path | Contents |
|---|---|
| `ntulearn/data/INDEX.md` | One page listing every course — **start here** to find the right course |
| `ntulearn/data/index.json` | Machine index: course IDs, counts, accessibility, paths |
| `ntulearn/data/digest/<courseId>.md` | **The main answer source.** Readable digest per course |
| `ntulearn/data/courses/<courseId>.json` | Full structured record when the digest is not precise enough |

If `NTULEARN_HOME` is set in the environment, the harvester lives there instead of at
`ntulearn/`; resolve the data directory against it. Never read or print
`.auth/state.json` — it is a live credential.

## How to answer

1. **Read `data/INDEX.md` first.** Match the user's wording (module code like `XX1234`,
   or a phrase like "data visualisation") to a course row.
2. **Read that course's digest** — `data/digest/<courseId>.md`.
   - Quizzes/tests with time limits, attempt rules and scope are under
     `## Quizzes / tests in detail`.
   - A summary table of every assessment is under `## Assessments`.
   - Course structure is under `## Content outline`.
   - Instructor notices are under `## Announcements`.
   - The user's own results are under `## My marks`.
3. **Fall back to `courses/<courseId>.json`** when you need an exact field, a raw value,
   or something the digest summarized away. The schema is documented in
   `references/data-model.md`.
4. **Always cite.** Every digest entry carries `Source (UI)` and often `Source (API)`
   lines. Give the user the UI link, plus the module path (e.g.
   `Unit 1: Foundations › Unit 1 Graded Quiz`) and the harvest timestamp. Never present
   a date or attempt count without saying which course it came from.

## Answering the common question shapes

**"Quiz 时间 / 次数 / 考试范围"** — read the assessment block in the course digest:

- *时间* has two distinct parts; report both, never merge them:
  - **Time limit** (答题时限), e.g. `5 minutes (auto-submits at the limit)`
  - **Due date** (截止时间), e.g. `25 Sept 2026, 11:59 pm` — may be `—` meaning no due date
- *次数* has two distinct parts; report both:
  - **Attempts allowed** (允许次数) — `Unlimited` when the API returns `attemptCount: -1`
  - **Attempts used** (已用次数) and how many remain, from the user's own record
- *考试范围* is the **Scope / description** block. It is instructor-written and is often
  the only place the coverage is stated. Quote it rather than paraphrasing.
  Supplementary signals: `Questions: N`, module path, and randomization notes.

**"What's due soon"** — scan the `## Assessments` tables of all courses for due dates,
sort by date, and state the local-time timestamp plus the course.

**"What's in <module>"** — use `## Content outline`, and preserve the indentation; it
encodes the folder/lesson hierarchy.

## Freshness — check before answering

The digest is a snapshot, not a live view. **Note the `Harvested` timestamp** at the top
of the digest (also in `data/INDEX.md`) when you answer.

- If the snapshot is **less than a day old**, answer directly.
- If it is **older**, say so explicitly and offer to refresh. Course content, due dates
  from announcements, and marks change during term.
- If the user asks something the snapshot cannot contain (a brand-new announcement, a
  just-released quiz, a live grade), refresh before answering.

### Refreshing

The skill ships a wrapper that checks the session first and refreshes when it can:

```bash
bash skills/ntulearn/scripts/refresh.sh
```

Or run the harvester directly (see `harvester/README.md`):

```bash
node src/status.mjs     # is the saved session still valid?
node src/harvest.mjs    # re-harvest every course into data/
```

If the session is **expired**, the user must re-authenticate interactively — NTU
federates to Microsoft Entra ID with MFA, so no script can do this:

```bash
node src/login.mjs      # opens a browser; the user signs in and completes MFA
```

Tell the user a browser window will open and they must finish the sign-in themselves.
Do not ask for their password — it is never needed or stored.

## Caveats to respect

- **A course with no access** shows a `> **Content unavailable.**` banner and a reason
  such as `User is not enrolled or membership is unavailable`. Report this as "your
  enrolment in this course isn't active yet" — it is a server-side state, not a failed
  harvest. Do not guess at that course's content.
- **`Time limit: none set`** means the instructor set no limit; it does not mean
  unlimited time in a practical sense (there may still be a due date).
- **`Questions are randomised`** means each attempt draws a different set; the scope text
  still describes the covered material.
- **Absent scope text** is common — many assessments simply have no description. Say so
  plainly instead of inventing coverage from the module title.
- **Announcement bodies may be truncated** in the digest. If the tail matters, read the
  full body from `courses/<courseId>.json`.
- **Never echo session cookies or `.auth/` contents.**
- **Marks and attempts are personal data.** Report them only to the account owner in this
  conversation.

## Do not

- Do not scrape NTULearn live to answer a single question — read the snapshot; refresh
  only when it is stale or the user asks.
- Do not present a `—` as if it were a real value; `—` means the field was empty.
- Do not assume the digest lists every quiz: an unreleased assessment will not be in the
  outline at all. If the user expects something that is missing, refresh first, then say
  it is not published to students.
