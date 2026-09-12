/**
 * Reconnaissance probe.
 *
 * Verifies the saved session and reports which Blackboard endpoints actually
 * answer for this account, with a small sample of each response shape. Run this
 * after `npm run login` and before writing/changing harvest logic, so the
 * harvester is built against real payloads instead of guesses.
 *
 * Run:  npm run probe
 */

import { createClient, ORIGIN, ROOT } from './lib/bb.mjs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const short = (value, n = 200) =>
  typeof value === 'string' ? value.slice(0, n) : JSON.stringify(value).slice(0, n);

async function main() {
  const client = await createClient();
  const report = {};

  console.log(`\n  Origin: ${ORIGIN}`);

  const me = await client.me();
  console.log(`  User  : ${me.userName}`);
  console.log(`  Name  : ${me.name?.given ?? ''} ${me.name?.family ?? ''}`);
  console.log(`  UUID  : ${me.uuid ?? me.id}`);
  report.me = me;

  // --- memberships -> courses -------------------------------------------
  const memberships = await client.get(
    `/learn/api/public/v1/users/${me.id}/courses?expand=course&limit=200&offset=0`,
  );
  const results = memberships?.results ?? [];
  console.log(`\n  Enrollments: ${results.length} (of ${memberships?.paging?.total ?? '?'})`);

  const courses = results
    .map((m) => ({
      membershipId: m.id,
      courseId: m.courseId,
      courseRoleId: m.courseRoleId,
      available: m.course?.availability?.available,
      ultraStatus: m.course?.ultraStatus,
      name: m.course?.name,
      displayName: m.course?.displayName ?? m.course?.name,
      externalId: m.course?.externalId,
    }))
    .filter((c) => c.available !== 'No');

  for (const c of courses) {
    console.log(`   - ${c.courseId.padEnd(18)} [${c.ultraStatus ?? '?'}] ${short(c.displayName, 70)}`);
  }
  report.courses = courses;

  if (!courses.length) {
    console.log('\n  No available courses found.');
  }

  // --- endpoint matrix on the first Ultra course -------------------------
  const target = courses.find((c) => c.ultraStatus === 'Ultra') ?? courses[0];
  if (target) {
    const cid = target.courseId;
    const uid = me.id;
    console.log(`\n  Probing endpoints against ${cid} (${short(target.displayName, 60)}):\n`);

    const candidates = [
      `/learn/api/public/v1/courses/${cid}`,
      `/learn/api/public/v1/courses/${cid}/contents?recursive=true&limit=200`,
      `/learn/api/public/v1/courses/${cid}/contents?limit=200`,
      `/learn/api/public/v1/courses/${cid}/announcements?limit=50`,
      `/learn/api/public/v1/courses/${cid}/gradebook/columns?limit=200`,
      `/learn/api/public/v1/courses/${cid}/gradebook/users/${uid}?limit=200`,
      `/learn/api/public/v1/courses/${cid}/members?limit=200`,
      `/learn/api/public/v1/courses/${cid}/groups?limit=200`,
      // Ultra-internal surfaces (undocumented; the Ultra UI uses these):
      `/learn/api/internal/courses/${cid}/assessments`,
      `/learn/api/internal/courses/${cid}/contents`,
      `/learn/api/internal/courses/${cid}/gradebook/columns`,
      `/learn/api/v1/courses/${cid}/assessments`,
    ];

    report.endpoints = {};
    for (const candidate of candidates) {
      let line;
      try {
        const data = await client.get(candidate);
        const count = data?.results?.length ?? (Array.isArray(data) ? data.length : undefined);
        line = `200  ${count !== undefined ? `(${count} results) ` : ''}${short(data, 160)}`;
        report.endpoints[candidate] = { status: 200, sample: data };
      } catch (error) {
        line = `${String(error.status ?? 'ERR').padEnd(4)} ${error.message.slice(0, 140)}`;
        report.endpoints[candidate] = { status: error.status ?? null, error: error.message };
      }
      console.log(`   ${candidate}\n     -> ${line}\n`);
    }
  }

  // --- what the browser revealed while logging in ------------------------
  try {
    const log = await readFile(path.join(ROOT, '.auth', 'network-log.jsonl'), 'utf8');
    const entries = log.trim().split('\n').filter(Boolean).map((l) => JSON.parse(l));
    const interesting = entries.filter((e) => /assess|quiz|test|content|attempt|grade/i.test(e.url));
    console.log(`  Browser network trace: ${entries.length} endpoints, ${interesting.length} content/assessment-related\n`);
    for (const e of interesting.slice(0, 60)) {
      console.log(`   ${String(e.status ?? '?').padEnd(4)} ${e.method.padEnd(5)} ${e.url.replace(ORIGIN, '')}`);
    }
    report.networkTrace = interesting;
  } catch {
    console.log('  (no browser network trace found — run `npm run login` and browse a few courses)');
  }

  const out = path.join(ROOT, '.auth', 'probe-report.json');
  const { writeFile } = await import('node:fs/promises');
  await writeFile(out, JSON.stringify(report, null, 2));
  console.log(`\n  Full report -> ${path.relative(process.cwd(), out)}\n`);
}

main().catch((error) => {
  console.error('\n  Probe failed:', error.message, '\n');
  process.exitCode = 1;
});
