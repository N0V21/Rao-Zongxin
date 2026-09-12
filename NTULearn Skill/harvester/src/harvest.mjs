/**
 * NTULearn harvester.
 *
 * Produces a local, citable snapshot of every course the account is enrolled in:
 *
 *   data/index.json            machine index of all courses
 *   data/courses/<id>.json     full structured record per course
 *   data/digest/<id>.md        readable digest — what the `ntulearn` skill answers from
 *   data/INDEX.md              one-page overview of every course
 *
 * Uses two API surfaces: the documented public REST API for course metadata and
 * announcements, and Ultra's `/learn/api/v1` surface for the outline, assessment
 * configuration, and the student's own attempts (see `lib/ultra.mjs`).
 *
 * Run:  npm run harvest
 */

import './env.mjs';
import { createClient, ROOT, ORIGIN } from './lib/bb.mjs';
import {
  walkOutline,
  fetchItemDetail,
  applyItemDetail,
  fetchColumnGrade,
  fetchAttempts,
  fetchColumns,
  fetchGrades,
  checkAccess,
  outlineUrl,
  assessmentUrl,
} from './lib/ultra.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const DATA_DIR = path.join(ROOT, 'data');
const COURSES_DIR = path.join(DATA_DIR, 'courses');
const DIGEST_DIR = path.join(DATA_DIR, 'digest');

const fmtDate = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('en-SG', {
    timeZone: 'Asia/Singapore',
    dateStyle: 'medium',
    timeStyle: 'short',
  });
};

/** Is this assessment a quiz/test rather than an assignment? */
const isQuizLike = (item) =>
  !/assignment|submission|project|report|presentation/i.test(
    `${item.assessment?.subtype ?? ''} ${item.title}`,
  );

/** Follow Blackboard's offset paging until every result is collected. */
async function getAll(client, url, { limit = 200, max = 2000 } = {}) {
  const collected = [];
  for (let offset = 0; offset < max; offset += limit) {
    const separator = url.includes('?') ? '&' : '?';
    const page = await client.get(`${url}${separator}limit=${limit}&offset=${offset}`);
    const results = page?.results ?? [];
    collected.push(...results);
    const total = page?.paging?.total;
    if (!results.length || results.length < limit) break;
    if (total !== undefined && collected.length >= total) break;
  }
  return collected;
}

/** Never treat a bare 403 as a dead session; only a login redirect or 401 is. */
async function tryGet(label, fn, fallback) {
  try {
    return await fn();
  } catch (error) {
    if (error.name === 'SessionExpiredError') throw error;
    console.warn(`      ! ${label}: ${error.message.slice(0, 110)}`);
    return fallback;
  }
}

/** Public-API content tree, used only for non-Ultra (Original) courses. */
function flattenPublicContents(nodes, parent = null, depth = 0, out = []) {
  for (const node of nodes ?? []) {
    out.push({
      contentId: node.id,
      courseId: node.courseId ?? '',
      title: node.title ?? '(untitled)',
      handler: node.contentHandler?.id ?? null,
      depth,
      breadcrumb: [],
      modulePath: '(course root)',
      description: node.description ?? null,
      dueDate: null,
      sources: { api: null, ui: outlineUrl(node.courseId ?? '', node.id) },
    });
    if (node.children?.length) flattenPublicContents(node.children, node.id, depth + 1, out);
  }
  return out;
}

/** Render one assessment as a markdown block, including its source links. */
function renderAssessment(item) {
  const lines = [];
  const a = item.assessment ?? {};

  lines.push(`#### ${item.title}`);
  lines.push('');
  lines.push(`- **Module**: ${item.modulePath}`);
  if (a.subtype || a.deployedAssessmentType) {
    lines.push(`- **Type**: ${a.subtype ?? a.deployedAssessmentType}`);
  }
  lines.push(
    `- **Due**: ${fmtDate(item.dueDate)}${item.settings?.isDueDateEnforced === false ? ' _(not enforced)_' : ''}`,
  );

  // Time limit — verified to be minutes.
  if (item.timeLimitMinutes != null) {
    lines.push(
      `- **Time limit**: ${item.timeLimitMinutes} minutes` +
        (item.timerCompletion === 'HARDSTOP' ? ' (auto-submits at the limit)' : ''),
    );
  } else {
    lines.push('- **Time limit**: none set');
  }

  // Attempts allowed.
  if (item.attempts) {
    lines.push(
      `- **Attempts allowed**: ${
        item.attempts.unlimited ? 'Unlimited' : (item.attempts.attemptCount ?? '—')
      }`,
    );
  }
  // Attempts actually used, from the student's own grade record.
  if (item.myAttempts) {
    const left = item.myAttempts.attemptsLeft;
    const remaining =
      left === -1 ? 'unlimited remaining' : left != null ? `${left} left` : 'remaining unknown';
    lines.push(
      `- **Attempts used**: ${item.myAttempts.used ?? '—'} (${remaining})` +
        (item.myAttempts.lastAttemptDate ? `, last on ${fmtDate(item.myAttempts.lastAttemptDate)}` : ''),
    );
  }
  if (item.myGrade) {
    let mark;
    if (item.myGrade.displayGrade != null) mark = `${item.myGrade.displayGrade}%`;
    else if (item.myGrade.effectiveScore != null) {
      mark = `${item.myGrade.effectiveScore} / ${item.myGrade.pointsPossible ?? '?'}`;
    } else mark = 'not yet marked';
    lines.push(`- **My mark**: ${mark} (status: ${item.myGrade.status ?? '—'})`);
  } else if (item.grading?.possible != null) {
    lines.push(`- **Points**: ${item.grading.possible}`);
  }

  if (a.questionCount != null) lines.push(`- **Questions**: ${a.questionCount}`);
  if (item.grading?.category) lines.push(`- **Gradebook category**: ${item.grading.category}`);

  if (item.settings?.isRandomizationOfQuestionsRequired) {
    lines.push('- **Questions are randomised**');
  }
  if (item.settings?.isRandomizationOfAnswersRequired === 'ALWAYS') {
    lines.push('- **Answer choices are randomised**');
  }
  if (item.settings?.isPasswordRequired) lines.push('- **Requires a password to start**');
  if (item.settings?.isSecureBrowserRequiredToTake) lines.push('- **Requires a secure browser**');
  if (item.settings?.isBacktrackingProhibited) lines.push('- **Cannot go back to previous questions**');

  if (item.exceptions?.length) {
    lines.push(`- **Personal accommodations**: ${JSON.stringify(item.exceptions)}`);
  }

  // Scope — the item description, which is where NTU instructors state coverage.
  if (item.description) {
    lines.push('');
    lines.push('**Scope / description:**');
    lines.push('');
    lines.push(`> ${item.description.replace(/\n/g, '\n> ')}`);
  }
  if (a.instructions && a.instructions !== item.description) {
    lines.push('');
    lines.push('**Instructions:**');
    lines.push('');
    lines.push(`> ${a.instructions.replace(/\n/g, '\n> ')}`);
  }

  lines.push('');
  lines.push(`- Source (UI): ${item.sources?.ui ?? '—'}`);
  if (item.sources?.api) lines.push(`- Source (API): ${item.sources.api}`);
  lines.push('');
  return lines.join('\n');
}

/** Build the per-course markdown digest the question-answering layer reads. */
function renderDigest(course) {
  const lines = [];
  lines.push(`# ${course.displayName}`);
  lines.push('');
  lines.push(`- **Course ID**: \`${course.courseId}\``);
  if (course.term) lines.push(`- **Term**: ${course.term}`);
  lines.push(`- **Experience**: ${course.ultraStatus ?? 'unknown'}`);
  lines.push(`- **Course home**: ${course.url}`);
  lines.push(`- **Harvested**: ${fmtDate(course.harvestedAt)}`);
  lines.push('');

  if (course.access && course.access.accessible === false) {
    lines.push('> **Content unavailable.** The server reported: ');
    lines.push(`> \`${course.access.reason}\``);
    lines.push('>');
    lines.push('> Your enrolment in this course is not currently active, so no outline,');
    lines.push('> assessments or announcements could be read. This is a server-side access');
    lines.push('> state, not a harvesting error.');
    lines.push('');
    return lines.join('\n');
  }

  const assessments = course.contentTree.filter((i) => i.assessment);
  const quizzes = assessments.filter(isQuizLike);
  const assignments = assessments.filter((a) => !isQuizLike(a));

  // --- assessments summary table ---------------------------------------
  lines.push('## Assessments');
  lines.push('');
  if (!assessments.length) {
    lines.push('_No assessments are published in the course outline._');
    lines.push('');
  } else {
    lines.push('| Title | Type | Due (SGT) | Time limit | Attempts | My mark | Points | Module |');
    lines.push('|---|---|---|---|---|---|---|---|');
    for (const item of assessments) {
      const attempts = item.attempts?.unlimited
        ? 'Unlimited'
        : (item.attempts?.attemptCount ?? '—');
      const limit = item.timeLimitMinutes != null ? `${item.timeLimitMinutes} min` : '—';
      const mark =
        item.myGrade?.displayGrade != null
          ? `${item.myGrade.displayGrade}%`
          : (item.myGrade?.effectiveScore ?? '—');
      lines.push(
        `| ${item.title} | ${item.assessment?.subtype ?? item.assessment?.deployedAssessmentType ?? '—'} | ${fmtDate(item.dueDate)} | ${limit} | ${attempts} | ${mark} | ${item.grading?.possible ?? '—'} | ${item.modulePath} |`,
      );
    }
    lines.push('');
  }

  if (quizzes.length) {
    lines.push('## Quizzes / tests in detail');
    lines.push('');
    for (const item of quizzes) lines.push(renderAssessment(item));
  }
  if (assignments.length) {
    lines.push('## Assignments in detail');
    lines.push('');
    for (const item of assignments) lines.push(renderAssessment(item));
  }

  // --- gradebook columns (includes non-content columns) ------------------
  if (course.gradebookColumns.length) {
    lines.push('## Gradebook columns');
    lines.push('');
    lines.push('| Column | Category | Due (SGT) | Points | Attempts |');
    lines.push('|---|---|---|---|---|');
    for (const column of course.gradebookColumns) {
      lines.push(
        `| ${column.name} | ${column.category ?? '—'} | ${fmtDate(column.dueDate)} | ${column.possible ?? '—'} | ${column.multipleAttempts ?? '—'} |`,
      );
    }
    lines.push('');
  }

  // --- outline ----------------------------------------------------------
  lines.push('## Content outline');
  lines.push('');
  for (const item of course.contentTree) {
    const indent = '  '.repeat(item.depth);
    const tag = item.assessment ? ` **[${item.assessment.subtype ?? 'assessment'}]**` : '';
    const snippet = item.description ? ` — ${item.description.replace(/\s+/g, ' ').slice(0, 110)}` : '';
    lines.push(`${indent}- ${item.title}${tag}${snippet}`);
  }
  lines.push('');

  // --- announcements ----------------------------------------------------
  if (course.announcements.length) {
    lines.push('## Announcements');
    lines.push('');
    for (const a of course.announcements) {
      lines.push(`### ${a.title ?? '(untitled)'} — ${fmtDate(a.created)}`);
      lines.push('');
      if (a.body) lines.push(a.body);
      lines.push('');
      lines.push(`- Source: ${a.url}`);
      lines.push('');
    }
  }

  // --- grades -----------------------------------------------------------
  const graded = course.contentTree.filter((i) => i.assessment && i.myGrade);
  if (graded.length) {
    lines.push('## My marks (per assessment)');
    lines.push('');
    lines.push('| Assessment | Mark | Status | Attempts used |');
    lines.push('|---|---|---|---|');
    for (const item of graded) {
      lines.push(
        `| ${item.title} | ${item.myGrade.displayGrade != null ? `${item.myGrade.displayGrade}%` : (item.myGrade.effectiveScore ?? '—')} | ${item.myGrade.status ?? '—'} | ${item.myAttempts?.used ?? '—'} |`,
      );
    }
    lines.push('');
  }

  return lines.join('\n');
}

async function harvestCourse(client, course, userId, harvestedAt) {
  console.log(`\n    ${course.courseId}  ${course.displayName}`);

  const access = await checkAccess(client, course.courseId);
  if (!access.accessible) {
    console.log(`      ! not accessible: ${access.reason}`);
    return {
      courseId: course.courseId,
      displayName: course.displayName,
      name: course.name,
      term: course.term,
      ultraStatus: course.ultraStatus,
      url: course.url,
      harvestedAt,
      access,
      contentTree: [],
      gradebookColumns: [],
      myGrades: [],
      announcements: [],
    };
  }

  const [announcements, columns, grades] = await Promise.all([
    tryGet(
      'announcements',
      () => getAll(client, `/learn/api/public/v1/courses/${course.courseId}/announcements`, { limit: 50 }),
      [],
    ),
    fetchColumns(client, course.courseId),
    fetchGrades(client, course.courseId),
  ]);

  let contentTree = [];
  if (course.ultraStatus === 'Ultra') {
    contentTree = await walkOutline(client, course.courseId);
  } else {
    const raw = await tryGet(
      'contents',
      () => getAll(client, `/learn/api/public/v1/courses/${course.courseId}/contents`, { limit: 100 }),
      [],
    );
    contentTree = flattenPublicContents(raw);
  }

  // Enrich every assessment: the outline endpoint blanks descriptions and
  // omits the student's own attempt usage, so each one needs a second call.
  const assessments = contentTree.filter((i) => i.assessment);
  for (const item of assessments) {
    const detail = await tryGet(
      `detail ${item.title}`,
      () => fetchItemDetail(client, course.courseId, item.contentId),
      null,
    );
    if (detail) {
      Object.assign(item, applyItemDetail(item, detail.raw));
      item.sources.api = `${ORIGIN}${detail.url}`;
    }

    const columnId = item.grading?.columnId;
    if (columnId) {
      const grade = await fetchColumnGrade(client, course.courseId, columnId, userId);
      if (grade) {
        item.myGrade = {
          status: grade.status ?? null,
          effectiveScore: grade.effectiveScore ?? null,
          displayGrade: grade.displayGrade?.score ?? null,
          pointsPossible: grade.pointsPossible ?? null,
        };
        // Keep every attempt so both "how many used" and their dates are answerable.
        const attempts = grade.id
          ? await tryGet(`attempts ${item.title}`, () => fetchAttempts(client, course.courseId, columnId, grade.id), [])
          : [];
        item.myAttempts = {
          used: attempts.length,
          attemptsLeft: grade.attemptsLeft ?? null,
          lastAttemptDate: attempts.map((a) => a.attemptDate).sort().at(-1) ?? null,
        };
      }
    }
  }

  console.log(
    `      outline: ${contentTree.length} items  assessments: ${assessments.length}  ` +
      `graded: ${assessments.filter((a) => a.myGrade).length}  announcements: ${announcements.length}`,
  );

  const gradeRows = Array.isArray(grades) ? grades : (grades?.results ?? []);

  return {
    courseId: course.courseId,
    displayName: course.displayName,
    name: course.name,
    term: course.term,
    ultraStatus: course.ultraStatus,
    externalId: course.externalId,
    description: course.description,
    url: course.url,
    harvestedAt,
    access,
    contentTree,
    gradebookColumns: columns.map((c) => ({
      id: c.id,
      name: c.name ?? c.columnName ?? null,
      contentId: c.contentId ?? null,
      dueDate: c.dueDate ?? null,
      possible: c.possible ?? null,
      category: c.gradebookCategory?.title ?? null,
      assessmentSubtype: c.assessmentSubtype ?? null,
      multipleAttempts: c.multipleAttempts ?? null,
      aggregationModel: c.aggregationModel ?? null,
      gradesReleased: c.gradesReleased ?? null,
    })),
    myGrades: gradeRows.map((g) => ({
      columnId: g.columnId ?? null,
      columnName: g.columnName ?? null,
      status: g.status ?? null,
      score: typeof g.score === 'object' ? (g.score?.value ?? null) : (g.score ?? null),
      scorePossible: typeof g.score === 'object' ? (g.score?.possible ?? null) : (g.possible ?? null),
      text: g.text ?? null,
      feedback: g.feedback ?? null,
    })),
    announcements: announcements.map((a) => ({
      id: a.id,
      title: a.title ?? null,
      body: a.body ?? null,
      created: a.created ?? null,
      url: `${ORIGIN}/ultra/courses/${course.courseId}/announcements`,
    })),
  };
}

async function resolveCourses(client, userId) {
  const memberships = await getAll(client, `/learn/api/public/v1/users/${userId}/courses?expand=course`);
  return memberships
    .map((m) => ({
      courseId: m.courseId,
      ultraStatus: m.course?.ultraStatus ?? null,
      name: m.course?.name ?? null,
      displayName: m.course?.displayName ?? m.course?.name ?? m.courseId,
      description: m.course?.description ?? null,
      externalId: m.course?.externalId ?? null,
      term: m.course?.term?.name ?? null,
      available: m.course?.availability?.available ?? null,
      url: outlineUrl(m.courseId),
    }))
    .filter((c) => c.available !== 'No');
}

async function main() {
  await mkdir(COURSES_DIR, { recursive: true });
  await mkdir(DIGEST_DIR, { recursive: true });

  const client = await createClient();
  const harvestedAt = new Date().toISOString();
  const me = await client.me();
  console.log(`\n  NTULearn harvest as ${me.userName}`);

  const courses = await resolveCourses(client, me.id);
  console.log(`  Courses: ${courses.length}`);

  const records = [];
  for (const course of courses) {
    records.push(await harvestCourse(client, course, me.id, harvestedAt));
  }

  for (const record of records) {
    await writeFile(path.join(COURSES_DIR, `${record.courseId}.json`), JSON.stringify(record, null, 2));
    await writeFile(path.join(DIGEST_DIR, `${record.courseId}.md`), renderDigest(record));
  }

  const index = {
    harvestedAt,
    origin: ORIGIN,
    user: { id: me.id, userName: me.userName, name: me.name },
    courseCount: records.length,
    courses: records.map((c) => ({
      courseId: c.courseId,
      displayName: c.displayName,
      term: c.term,
      ultraStatus: c.ultraStatus,
      accessible: c.access?.accessible !== false,
      inaccessibleReason: c.access?.accessible === false ? c.access.reason : null,
      contentItems: c.contentTree.length,
      assessments: c.contentTree.filter((i) => i.assessment).length,
      announcements: c.announcements.length,
      digest: `digest/${c.courseId}.md`,
      url: c.url,
    })),
  };
  await writeFile(path.join(DATA_DIR, 'index.json'), JSON.stringify(index, null, 2));

  const overview = [
    '# NTULearn — all courses',
    '',
    `- **Account**: ${me.userName} (${me.name?.given ?? ''} ${me.name?.family ?? ''})`,
    `- **Harvested**: ${fmtDate(harvestedAt)}`,
    `- **Courses**: ${records.length}`,
    '',
    '| Course | Term | Items | Assessments | Status | Digest |',
    '|---|---|---|---|---|---|',
    ...records.map(
      (c) =>
        `| ${c.displayName} | ${c.term ?? '—'} | ${c.contentTree.length} | ${c.contentTree.filter((i) => i.assessment).length} | ${c.access?.accessible === false ? 'no access' : 'ok'} | [\`${c.courseId}\`](digest/${c.courseId}.md) |`,
    ),
    '',
  ].join('\n');
  await writeFile(path.join(DATA_DIR, 'INDEX.md'), overview);
  await writeFile(path.join(DATA_DIR, 'request-log.json'), JSON.stringify(client.requestLog, null, 2));

  console.log(`\n  Wrote ${records.length} course records + digests -> data/`);
  console.log(`  Requests: ${client.requestLog.length}\n`);
}

main().catch((error) => {
  console.error('\n  Harvest failed:', error.message, '\n');
  process.exitCode = 1;
});
