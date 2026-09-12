# Harvester

Turns an NTULearn (Blackboard Learn Ultra) account into a local, citable snapshot of
every enrolled course — content, quizzes and tests, due dates, attempt rules, exam
scope, announcements and marks.

The `ntulearn` skill (`../skills/ntulearn/`) reads that snapshot to answer questions.

## Why there is no password login

NTU federates NTULearn to **Microsoft Entra ID with MFA enforced**. A scripted
username/password login cannot complete that flow, and retrying it risks locking the
account. So authentication is done once by a human in a real browser, and only the
resulting **session cookies** are stored.

**The password is never needed, never read, and never written to disk.**

## Setup

```bash
npm install
npx playwright install chromium     # ~150 MB, into ../.browsers
```

## Usage

### 1. Log in (once per session lifetime)

```bash
npm run login
```

A browser window opens. Sign in with your NTU credentials, complete MFA, tick
"Stay signed in", then click into a couple of courses. The script detects the
authenticated session, saves it to `.auth/state.json` (mode `0600`) and writes a
network trace to `.auth/network-log.jsonl`.

The persistent browser profile in `.auth/profile/` keeps Entra's "stay signed in"
state, so repeat logins are usually just a click.

### 2. Harvest

```bash
npm run status     # verify the session without opening a browser
npm run harvest    # write data/
```

Output:

```
data/
├── INDEX.md                 overview of all courses
├── index.json               machine index
├── digest/<courseId>.md     readable per-course digest (the answer source)
├── courses/<courseId>.json  full structured record
└── request-log.json         every API URL the harvest touched
```

### 3. Maintenance

```bash
npm run discover                        # re-map the Ultra API surface
npm run verify <courseId> <contentId>   # print a real assessment page + its API calls
```

Run these after a Blackboard upgrade if the harvest starts returning empty outlines or
missing assessments.

## How it works

Two API surfaces, both authenticated by the captured cookies:

- **`/learn/api/public/v1/…`** — the documented public REST API. Used for the course
  list and announcements. Its `courses/{id}/contents` and `gradebook` endpoints return
  almost nothing useful for Ultra courses.
- **`/learn/api/v1/…`** — the undocumented surface the Ultra SPA itself calls. Used for
  the outline, assessment configuration, attempt records and marks.

The two are **not interchangeable**: the outline endpoint (`contents/{id}/children`)
returns assessment summaries with blank descriptions, while the single-item endpoint
(`contents/{id}`) carries the description — which is exactly where instructors write the
exam scope. The harvester calls both.

Field units were verified against the rendered UI rather than assumed:

| API value | UI text | Conclusion |
|---|---|---|
| `deploymentSettings.timeLimit: 5` | "Time limit: 5 minutes" | the field is **minutes** |
| `deploymentSettings.attemptCount: -1` | "Attempts: Unlimited" | `-1` means **unlimited** |
| `gradingColumn.dueDate: …T15:59:00Z` | "…11:59 PM (UTC+8)" | ISO UTC, localised for display |

## Layout

```
src/
├── env.mjs        keeps the bundled browser inside the workspace
├── lib/bb.mjs     cookie-aware HTTP client + session loading
├── lib/ultra.mjs  Ultra content API, normalization, unit handling
├── login.mjs      interactive SSO capture
├── status.mjs     session validity check
├── harvest.mjs    the main harvest → data/
├── discover.mjs   re-map the Ultra endpoints from live traffic
└── verify.mjs     check API fields against the rendered page
```

## Security notes

- `.auth/` and `data/` are git-ignored. `.auth/state.json` is equivalent to being logged
  in — treat it as a credential, and delete it when you are done with it.
- Session lifetime is set by NTU, not by this tool. When `npm run status` reports
  `EXPIRED`, re-run `npm run login`.
- Harvested content is your own coursework. It is stored locally and never transmitted
  anywhere. Do not commit it — it contains your marks and your instructors' materials.

## Adapting to another institution

The endpoints in `lib/ultra.mjs` are generic Blackboard Learn Ultra, not NTU-specific —
only the origin and the SSO flow are. To target another institution, change `ORIGIN` in
`lib/bb.mjs`, point `login.mjs` at that instance's URL, and re-run `npm run discover` to
confirm the endpoint shapes still match.
