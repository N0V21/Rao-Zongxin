/**
 * Field-mapping verifier.
 *
 * Opens a real Ultra assessment page in a headless browser and prints the text
 * the student actually sees, so the values the harvester reads out of the API can
 * be checked against the UI. Use this whenever a Blackboard upgrade might have
 * changed a field name or unit.
 *
 * Run:  node src/verify.mjs <courseId> <contentId>
 */

import './env.mjs';
import { chromium } from 'playwright';
import { loadStorageState, ORIGIN, ROOT } from './lib/bb.mjs';
import { outlineUrl } from './lib/ultra.mjs';
import path from 'node:path';

const [courseId, contentId] = process.argv.slice(2);
if (!courseId) {
  console.error('Usage: node src/verify.mjs <courseId> [contentId]');
  process.exit(1);
}

const url = outlineUrl(courseId, contentId);
console.log(`\n  Opening ${url}\n`);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  storageState: await loadStorageState(),
  viewport: { width: 1600, height: 1200 },
  locale: 'en-SG',
  timezoneId: 'Asia/Singapore',
});
const page = await context.newPage();

// Capture the assessment detail calls the page makes; this is where a time limit
// or attempt setting would show up if the outline endpoint omitted it.
const apiHits = [];
page.on('response', async (response) => {
  const responseUrl = response.url();
  if (!responseUrl.startsWith(ORIGIN) || !responseUrl.includes('/learn/api/')) return;
  const type = response.headers()['content-type'] ?? '';
  if (!type.includes('json')) return;
  let body = null;
  try {
    body = (await response.text()).slice(0, 20_000);
  } catch {
    /* ignore */
  }
  apiHits.push({ url: responseUrl.replace(ORIGIN, ''), status: response.status(), body });
});

await page.goto(url, { waitUntil: 'networkidle', timeout: 60_000 }).catch((e) => console.log('  nav:', e.message));
await page.waitForTimeout(6000);

// The assessment info panel may need a click to expand.
for (const label of ['Details & Actions', 'Assessment details', 'Show details']) {
  const control = page.getByText(label, { exact: false }).first();
  if (await control.count().catch(() => 0)) {
    await control.click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(1500);
  }
}

const text = await page.evaluate(() => document.body.innerText).catch(() => '');
console.log('  ===== VISIBLE PAGE TEXT (trimmed) =====\n');
console.log(
  text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .slice(0, 120)
    .join('\n'),
);

console.log('\n  ===== API CALLS MADE BY THE PAGE =====\n');
for (const hit of apiHits) {
  const timeLimit = hit.body?.match(/"timeLimit"\s*:\s*[^,}]+/)?.[0];
  const attempts = hit.body?.match(/"attemptCount"\s*:\s*[^,}]+/)?.[0];
  console.log(`  ${hit.status} ${hit.url.slice(0, 120)}`);
  if (timeLimit || attempts) console.log(`      ${timeLimit ?? ''} ${attempts ?? ''}`);
}

const screenshotPath = path.join(ROOT, '.auth', 'verify-quiz.png');
await page.screenshot({ path: screenshotPath, fullPage: false }).catch(() => {});
console.log(`\n  Screenshot -> ${path.relative(process.cwd(), screenshotPath)}\n`);

await browser.close();
