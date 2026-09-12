/**
 * Endpoint discovery.
 *
 * Loads each Ultra course outline in a headless browser using the saved session
 * and records every JSON API call the Ultra SPA makes, together with a sample of
 * its response body. Ultra keeps assessment metadata (attempts allowed, time
 * limit, availability window) behind internal endpoints that are not part of the
 * public REST API, so this is how we learn the real contract instead of guessing.
 *
 * Run:  npm run discover
 * Output: .auth/discovery.json
 */

import './env.mjs';
import { chromium } from 'playwright';
import { loadStorageState, ORIGIN, ROOT } from './lib/bb.mjs';
import { createClient } from './lib/bb.mjs';
import { writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const OUT = path.join(ROOT, '.auth', 'discovery.json');
const MAX_BODY = 60_000;

async function main() {
  await mkdir(path.dirname(OUT), { recursive: true });
  const state = await loadStorageState();
  const client = await createClient();
  const me = await client.me();
  const memberships = await client.get(
    `/learn/api/public/v1/users/${me.id}/courses?expand=course&limit=200`,
  );
  const courses = (memberships.results ?? [])
    .filter((m) => m.course?.availability?.available !== 'No')
    .map((m) => ({ courseId: m.courseId, name: m.course?.displayName ?? m.courseId }));

  console.log(`\n  Discovering endpoints across ${courses.length} courses…\n`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    storageState: state,
    viewport: { width: 1600, height: 1000 },
    locale: 'en-SG',
    timezoneId: 'Asia/Singapore',
  });

  const captured = new Map();
  context.on('response', async (response) => {
    const url = response.url();
    if (!url.startsWith(ORIGIN)) return;
    if (!url.includes('/learn/api/')) return;
    const key = `${response.request().method()} ${url.split('?')[0]}`;
    if (captured.has(key)) return;

    const contentType = response.headers()['content-type'] ?? '';
    if (!contentType.includes('json')) return;

    let body = null;
    try {
      const text = await response.text();
      body = text.length > MAX_BODY ? `${text.slice(0, MAX_BODY)}…[truncated]` : text;
    } catch {
      /* body unavailable */
    }
    captured.set(key, {
      method: response.request().method(),
      url,
      status: response.status(),
      body,
    });
  });

  const page = await context.newPage();
  for (const course of courses) {
    console.log(`    ${course.courseId}  ${course.name.slice(0, 60)}`);
    try {
      await page.goto(`${ORIGIN}/ultra/courses/${course.courseId}/outline`, {
        waitUntil: 'networkidle',
        timeout: 45_000,
      });
      // Let the SPA settle and fire its deferred content/gradebook calls.
      await page.waitForTimeout(4000);
      // Scroll to encourage lazy-loaded list items.
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)).catch(() => {});
      await page.waitForTimeout(1500);
    } catch (error) {
      console.log(`      ! ${error.message.slice(0, 100)}`);
    }
  }

  // Also open the gradebook view, which is where Ultra surfaces assessment
  // configuration such as due dates and attempts.
  for (const course of courses.slice(0, 3)) {
    for (const view of ['gradebook', 'grades']) {
      try {
        await page.goto(`${ORIGIN}/ultra/courses/${course.courseId}/${view}`, {
          waitUntil: 'networkidle',
          timeout: 45_000,
        });
        await page.waitForTimeout(3500);
      } catch {
        /* view may not exist for this role */
      }
    }
  }

  await browser.close();

  const entries = [...captured.values()].sort((a, b) => a.url.localeCompare(b.url));
  await writeFile(OUT, JSON.stringify({ discoveredAt: new Date().toISOString(), entries }, null, 2));

  console.log(`\n  Captured ${entries.length} distinct JSON endpoints -> .auth/discovery.json\n`);
  for (const e of entries) {
    console.log(`    ${String(e.status).padEnd(4)} ${e.method.padEnd(5)} ${e.url.replace(ORIGIN, '').slice(0, 130)}`);
  }
  console.log();
}

main().catch((error) => {
  console.error('\n  Discovery failed:', error.message, '\n');
  process.exitCode = 1;
});
