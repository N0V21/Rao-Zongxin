/**
 * Blackboard Learn **Ultra** content API.
 *
 * The documented public REST API (`/learn/api/public/v1/...`) only exposes an
 * outline skeleton for Ultra courses: titles but none of the assessment
 * configuration, and its gradebook endpoints come back empty. The Ultra SPA
 * itself uses a second, undocumented surface under `/learn/api/v1/`, which is
 * what this module drives.
 *
 * Two different payloads matter, and they are not interchangeable:
 *   - `contents/{id}/children` — the outline. Cheap, but descriptions are blank.
 *   - `contents/{id}`          — one item in full. Carries the description
 *                                (which is where instructors write the exam scope),
 *                                question count, and per-student exceptions.
 *
 * Field units were verified against the rendered UI (`npm run verify`): the
 * `timeLimit` field is **minutes**, and `attemptCount: -1` means unlimited.
 *
 * Re-confirm with `npm run discover` after a Blackboard upgrade.
 */

export const ORIGIN = 'https://ntulearn.ntu.edu.sg';

/** Query the Ultra UI uses when loading the course outline. */
const OUTLINE_QUERY =
  '@view=Summary&expand=assignedGroups,selfEnrollmentGroups.group,gradebookCategory&includeInActivityTracking=true';

/** Query the Ultra UI uses when opening a single content item. */
const ITEM_QUERY =
  'expand=assignedGroups,selfEnrollmentGroups.group,alignedGoals,gradebookCategory&includeInActivityTracking=false';

/** Content handlers that represent a graded assessment the student can take. */
export const ASSESSMENT_HANDLERS = new Set([
  'resource/x-bb-asmt-test-link',
  'resource/x-bb-assessment',
  'resource/x-bb-asmt-survey-link',
]);

/** Handlers that can contain children and must be walked into. */
const CONTAINER_HANDLERS = new Set([
  'resource/x-bb-folder',
  'resource/x-bb-lesson',
  'resource/x-bb-module',
  'resource/x-bb-learning-module',
]);

/** Ultra deep link to the course outline, optionally focused on one item. */
export function outlineUrl(courseId, contentId) {
  const base = `${ORIGIN}/ultra/courses/${courseId}/outline`;
  return contentId ? `${base}?contentId=${contentId}` : base;
}

/** Ultra deep link to an assessment's student-facing overview page. */
export function assessmentUrl(courseId, contentId) {
  return `${ORIGIN}/ultra/courses/${courseId}/assessment/${contentId}/overview?courseId=${courseId}`;
}

/** Strip Blackboard's HTML wrapper down to readable text. */
export function htmlToText(html) {
  if (!html) return null;
  const text = String(html)
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|tr|h[1-6])>/gi, '\n')
    .replace(/<li[^>]*>/gi, '  • ')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  return text || null;
}

/** Read one folder/lesson's direct children. */
export async function fetchChildren(client, courseId, itemId, { limit = 200 } = {}) {
  const url = `/learn/api/v1/courses/${courseId}/contents/${itemId}/children?${OUTLINE_QUERY}&limit=${limit}`;
  const page = await client.get(url);
  return { results: page?.results ?? [], paging: page?.paging ?? null, url };
}

/** Read one content item in full — this is where descriptions and question counts live. */
export async function fetchItemDetail(client, courseId, contentId) {
  const url = `/learn/api/v1/courses/${courseId}/contents/${contentId}?${ITEM_QUERY}`;
  return { raw: await client.get(url), url };
}

/**
 * Walk the whole Ultra outline depth-first.
 *
 * @returns {Promise<Array<object>>} normalized items, each carrying the breadcrumb
 *   of its ancestor module titles so a question can be answered in context.
 */
export async function walkOutline(client, courseId, { maxDepth = 8 } = {}) {
  const items = [];
  const visited = new Set();

  async function walk(itemId, breadcrumb, depth) {
    if (depth > maxDepth || visited.has(itemId)) return;
    visited.add(itemId);

    let page;
    try {
      page = await fetchChildren(client, courseId, itemId);
    } catch (error) {
      if (error.name === 'SessionExpiredError') throw error;
      return; // A folder the student cannot read is simply skipped.
    }

    for (const raw of page.results) {
      items.push(normalizeItem(raw, { courseId, breadcrumb, depth, apiUrl: page.url }));

      const isContainer =
        CONTAINER_HANDLERS.has(raw.contentHandler) ||
        raw.hasChildren === true ||
        (raw.contentDetail?.['resource/x-bb-folder']?.hasChildren ?? false);

      if (isContainer) {
        await walk(raw.id, [...breadcrumb, raw.title], depth + 1);
      }
    }
  }

  await walk('ROOT', [], 0);
  return items;
}

/** Pull the `test` sub-object out of an item's `contentDetail`, whatever the handler. */
function testOf(raw) {
  const handler = raw?.contentHandler ?? null;
  const detail = raw?.contentDetail
    ? (raw.contentDetail[handler] ?? Object.values(raw.contentDetail)[0])
    : null;
  return { handler, detail, test: detail?.test ?? null };
}

/** Convert an Ultra outline payload into the flat, question-ready record. */
export function normalizeItem(raw, { courseId, breadcrumb = [], depth = 0, apiUrl = null }) {
  const { handler, detail, test } = testOf(raw);
  const deployment = test?.deploymentSettings ?? null;
  const column = test?.gradingColumn ?? null;
  const assessment = test?.assessment ?? null;
  const isAssessment = ASSESSMENT_HANDLERS.has(handler) && !!test;

  return {
    contentId: raw.id,
    courseId,
    title: raw.title ?? '(untitled)',
    handler,
    renderType: raw.renderType ?? null,
    depth,
    breadcrumb,
    modulePath: breadcrumb.length ? breadcrumb.join(' › ') : '(course root)',
    description: htmlToText(raw.description ?? detail?.description),
    visibility: raw.visibility ?? null,
    isGroupContent: raw.isGroupContent ?? null,
    dueDate: raw.genericReadOnlyData?.dueDate ?? column?.dueDate ?? null,
    dueDateExceptionType: raw.dueDateExceptionType ?? null,
    hasGradeColumn: raw.genericReadOnlyData?.hasGradeColumn ?? false,
    ...(isAssessment
      ? {
          assessment: {
            id: assessment?.id ?? null,
            type: assessment?.type ?? null,
            subtype: assessment?.subtype ?? null,
            deployedAssessmentType: test?.deployedAssessmentType ?? null,
            title: assessment?.title ?? raw.title ?? null,
            instructions: htmlToText(assessment?.instructions?.rawText),
            description: htmlToText(assessment?.description?.rawText),
            lastModified: assessment?.lastModifiedDate ?? null,
            questionCount: assessment?.questionCount ?? null,
            totalPoints: assessment?.totalPoints ?? null,
          },
          attempts: {
            // -1 from the Ultra API means unlimited attempts.
            attemptCount: deployment?.attemptCount ?? null,
            unlimited: deployment?.attemptCount === -1,
          },
          grading: {
            possible: column?.possible ?? null,
            category: column?.gradebookCategory?.title ?? null,
            assessmentSubtype: column?.assessmentSubtype ?? null,
            aggregationModel: column?.aggregationModel ?? null,
            isAttemptBased: column?.isAttemptBased ?? null,
            gradesReleased: column?.gradesReleased ?? null,
            enforceDueDate: column?.enforceDueDate ?? null,
            columnId: column?.id ?? null,
            scorable: column?.scorable ?? null,
          },
          /** Verified in minutes. Null when the instructor set no time limit. */
          timeLimitMinutes: deployment?.timeLimit ?? null,
          /** HARDSTOP = auto-submit at the limit; CONTINUAL = keep going. */
          timerCompletion: deployment?.timerCompletion ?? null,
          /** Per-student accommodations, when the instructor granted any. */
          exceptions: test?.exceptions ?? null,
          settings: deployment
            ? {
                isDueDateEnforced: deployment.isDueDateEnforced ?? null,
                isPasswordRequired: deployment.isPasswordRequired ?? null,
                isSecureBrowserRequiredToTake: deployment.isSecureBrowserRequiredToTake ?? null,
                isRandomizationOfQuestionsRequired: deployment.isRandomizationOfQuestionsRequired ?? null,
                isRandomizationOfAnswersRequired: deployment.isRandomizationOfAnswersRequired ?? null,
                isBacktrackingProhibited: deployment.isBacktrackingProhibited ?? null,
                isCompletionForced: deployment.isCompletionForced ?? null,
                isScoreShown: deployment.isScoreShown ?? null,
                isCorrectAnswerShown: deployment.isCorrectAnswerShown ?? null,
                isFeedbackShown: deployment.isFeedbackShown ?? null,
                isLateAttemptCreationDisallowed: deployment.isLateAttemptCreationDisallowed ?? null,
              }
            : null,
        }
      : {}),
    sources: {
      api: apiUrl ? `${ORIGIN}${apiUrl}` : null,
      ui: isAssessment ? assessmentUrl(courseId, raw.id) : outlineUrl(courseId, raw.id),
    },
  };
}

/**
 * Merge the single-item payload into an outline record.
 *
 * The outline endpoint blanks out `description`, which is precisely where the
 * exam scope is written, so every assessment needs this second call.
 */
export function applyItemDetail(item, raw) {
  const { test } = testOf(raw);
  const assessment = test?.assessment ?? null;
  const deployment = test?.deploymentSettings ?? null;

  // Item-level description is the authoritative scope text; the assessment's own
  // description/instructions are usually empty on NTU courses.
  const scope =
    htmlToText(raw?.description) ??
    htmlToText(assessment?.instructions?.rawText) ??
    htmlToText(assessment?.description?.rawText);

  if (!item.assessment) {
    return { ...item, description: scope ?? item.description };
  }

  return {
    ...item,
    description: scope ?? item.description,
    dueDate: raw?.genericReadOnlyData?.dueDate ?? item.dueDate,
    assessment: {
      ...item.assessment,
      instructions: htmlToText(assessment?.instructions?.rawText) ?? item.assessment.instructions,
      description: htmlToText(assessment?.description?.rawText) ?? item.assessment.description,
      questionCount: assessment?.questionCount ?? item.assessment.questionCount,
      totalPoints: assessment?.totalPoints ?? item.assessment.totalPoints,
    },
    attempts: {
      ...item.attempts,
      attemptCount: deployment?.attemptCount ?? item.attempts.attemptCount,
      unlimited: (deployment?.attemptCount ?? item.attempts.attemptCount) === -1,
    },
    timeLimitMinutes: deployment?.timeLimit ?? item.timeLimitMinutes ?? null,
    timerCompletion: deployment?.timerCompletion ?? item.timerCompletion ?? null,
    exceptions: test?.exceptions ?? item.exceptions ?? null,
  };
}

/** The student's own grade for one gradebook column, including attempts consumed. */
export async function fetchColumnGrade(client, courseId, columnId, userId) {
  try {
    const page = await client.get(
      `/learn/api/v1/courses/${courseId}/gradebook/columns/${columnId}/grades?expand=attemptsLeft&userId=${userId}`,
    );
    return page?.results?.[0] ?? null;
  } catch (error) {
    if (error.name === 'SessionExpiredError') throw error;
    return null;
  }
}

/**
 * Every attempt the student has made on one gradebook column.
 *
 * `attemptsLeft` alone cannot distinguish "0 used" from "unlimited", so the real
 * count comes from this sub-resource.
 */
export async function fetchAttempts(client, courseId, columnId, gradeId) {
  try {
    const page = await client.get(
      `/learn/api/v1/courses/${courseId}/gradebook/columns/${columnId}/grades/${gradeId}/attempts?fields=id,status,attemptDate,exempt,overrideStatus`,
    );
    return page?.results ?? [];
  } catch (error) {
    if (error.name === 'SessionExpiredError') throw error;
    return [];
  }
}

/** The student's own grades across the course. */
export async function fetchGrades(client, courseId) {
  try {
    return await client.get(`/learn/api/v1/courses/${courseId}/gradebook/grades`);
  } catch (error) {
    if (error.name === 'SessionExpiredError') throw error;
    return null;
  }
}

/** Gradebook columns (due dates, points, categories) from the Ultra gradebook. */
export async function fetchColumns(client, courseId) {
  try {
    const page = await client.get(
      `/learn/api/v1/courses/${courseId}/gradebook/columns?expand=gradebookCategory,associatedRubrics,collectExternalSubmissions&limit=200`,
    );
    return page?.results ?? [];
  } catch (error) {
    if (error.name === 'SessionExpiredError') throw error;
    return [];
  }
}

/** Whether the student's membership in this course is currently active. */
export async function checkAccess(client, courseId) {
  try {
    await client.get(`/learn/api/v1/courses/${courseId}/contents/ROOT`);
    return { accessible: true, reason: null };
  } catch (error) {
    if (error.name === 'SessionExpiredError') throw error;
    let reason = null;
    try {
      reason = JSON.parse(error.message.slice(error.message.indexOf('{')))?.message ?? null;
    } catch {
      /* keep null */
    }
    return { accessible: false, reason: reason ?? `HTTP ${error.status}` };
  }
}
