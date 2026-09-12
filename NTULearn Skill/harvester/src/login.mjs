/**
 * One-time interactive login for NTULearn.
 *
 * NTU federates Blackboard to Microsoft Entra ID with MFA enforced, so no
 * scripted username/password login can complete the flow. Instead this opens a
 * real browser, lets the human finish SSO + MFA by hand, then captures the
 * resulting session cookies plus a network trace of the API calls the browser
 * makes while browsing.
 *
 * Run:  npm run login
 */

import './env.mjs';
import { chromium } from 'playwright';
import { mkdir, writeFile, chmod } from 'node:fs/promises';
import { ORIGIN, PROFILE_DIR, STATE_PATH, ROOT } from './lib/bb.mjs';
import path from 'node:path';

const TIMEOUT_MS = Number(process.env.NTULEARN_LOGIN_TIMEOUT_MS ?? 15 * 60 * 1000);
const POLL_MS = 3000;
const NETWORK_LOG = path.join(ROOT, '.auth', 'network-log.jsonl');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  await mkdir(path.dirname(STATE_PATH), { recursive: true });

  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless: false,
    viewport: { width: 1440, height: 900 },
    locale: 'en-SG',
    timezoneId: 'Asia/Singapore',
    args: ['--disable-blink-features=AutomationControlled'],
  });

  const page = context.pages()[0] ?? (await context.newPage());

  // Record every API-ish call the browser makes. After a successful login this
  // trace is how we discover Ultra's internal assessment endpoints, which the
  // public REST API does not expose.
  const observed = [];
  context.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith(ORIGIN)) return;
    if (!/\/(learn\/api|webapps|ultra)\//.test(url)) return;
    observed.push({
      method: request.method(),
      url,
      resourceType: request.resourceType(),
      postData: request.postData()?.slice(0, 2000) ?? null,
    });
  });
  context.on('response', async (response) => {
    const url = response.url();
    if (!url.startsWith(ORIGIN)) return;
    if (!/\/(learn\/api|webapps|ultra)\//.test(url)) return;
    const entry = observed.find((o) => o.url === url && o.status === undefined);
    if (entry) entry.status = response.status();
  });

  console.log('\n  Opening NTULearn…\n');
  await page.goto(`${ORIGIN}/ultra`, { waitUntil: 'domcontentloaded' }).catch(() => {});

  console.log('  ┌──────────────────────────────────────────────────────────────┐');
  console.log('  │  A browser window is opening (or is already open).           │');
  console.log('  │                                                              │');
  console.log('  │  1. Sign in with your NTU account and complete MFA.          │');
  console.log('  │  2. Tick "Stay signed in" if offered.                        │');
  console.log('  │  3. Once the course list appears, CLICK INTO 2-3 COURSES,    │');
  console.log('  │     and open one quiz so the assessment pages load.          │');
  console.log('  │  4. Then just wait — this script saves the session by itself. │');
  console.log('  │                                                              │');
  console.log(`  │  Waiting up to ${Math.round(TIMEOUT_MS / 60000)} minutes…`.padEnd(65) + '│');
  console.log('  └──────────────────────────────────────────────────────────────┘\n');

  const deadline = Date.now() + TIMEOUT_MS;
  let user = null;

  while (Date.now() < deadline) {
    await sleep(POLL_MS);
    if (context.pages().length === 0) {
      console.error('\n  Browser window was closed before login completed. Aborting.\n');
      process.exitCode = 1;
      return;
    }
    // Only same-origin pages can answer this probe; during SSO we are on
    // login.microsoftonline.com and simply keep waiting.
    for (const p of context.pages()) {
      if (!p.url().startsWith(ORIGIN)) continue;
      try {
        user = await p.evaluate(async (origin) => {
          const res = await fetch(`${origin}/learn/api/public/v1/users/me`, {
            credentials: 'include',
            headers: { accept: 'application/json' },
          });
          return res.ok ? await res.json() : null;
        }, ORIGIN);
      } catch {
        /* page navigating; retry next tick */
      }
      if (user) break;
    }
    if (user) break;
    process.stdout.write('.');
  }

  if (!user) {
    console.error('\n\n  Timed out before an authenticated session appeared. Re-run `npm run login`.\n');
    process.exitCode = 1;
    await context.close();
    return;
  }

  console.log(`\n\n  Authenticated as ${user.userName} (${user.name?.given ?? ''} ${user.name?.family ?? ''})`.trim());

  // Persist user + the network trace first, so an export hiccup cannot lose them.
  await writeFile(
    path.join(ROOT, '.auth', 'user.json'),
    JSON.stringify({ capturedAt: new Date().toISOString(), user }, null, 2),
  );
  const unique = new Map();
  for (const entry of observed) {
    const key = `${entry.method} ${entry.url.split('?')[0]}`;
    if (!unique.has(key)) unique.set(key, entry);
  }
  await writeFile(
    NETWORK_LOG,
    [...unique.values()].map((e) => JSON.stringify(e)).join('\n') + '\n',
  );
  console.log(`  Captured ${unique.size} distinct API endpoints -> .auth/network-log.jsonl`);

  await context.storageState({ path: STATE_PATH });
  await chmod(STATE_PATH, 0o600);
  console.log(`  Session saved -> ${path.relative(process.cwd(), STATE_PATH)}`);

  await context.close();
  console.log('\n  Done. Next: `npm run probe` to verify, then `npm run harvest`.\n');
}

main().catch((error) => {
  console.error('\n  Login failed:', error.message, '\n');
  process.exitCode = 1;
});
