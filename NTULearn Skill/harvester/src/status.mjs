/**
 * Check whether the saved NTULearn session is still valid, without opening a
 * browser. Cheap enough to run before any question about course content.
 *
 * Run:  npm run status
 * Exit: 0 valid, 2 missing/expired, 1 unexpected failure
 */

import { createClient, STATE_PATH, ROOT } from './lib/bb.mjs';
import { existsSync } from 'node:fs';
import { stat } from 'node:fs/promises';
import path from 'node:path';

async function main() {
  if (!existsSync(STATE_PATH)) {
    console.log('\n  Session: MISSING — run `npm run login`.\n');
    process.exitCode = 2;
    return;
  }

  const client = await createClient();
  const me = await client.me();
  const capturedAt = (await stat(STATE_PATH)).mtimeMs;
  const ageMinutes = Math.round((Date.now() - capturedAt) / 60000);

  console.log('\n  Session: VALID');
  console.log(`  User   : ${me.userName} (${me.name?.given ?? ''} ${me.name?.family ?? ''})`);
  console.log(`  Captured: ${ageMinutes} min ago`);
  console.log(`  State  : ${path.relative(ROOT, STATE_PATH)}`);

  const indexPath = path.join(ROOT, 'data', 'index.json');
  if (existsSync(indexPath)) {
    const { readFile } = await import('node:fs/promises');
    const index = JSON.parse(await readFile(indexPath, 'utf8'));
    const ageHours = ((Date.now() - new Date(index.harvestedAt).getTime()) / 3_600_000).toFixed(1);
    console.log(`  Snapshot: ${index.courseCount} courses, harvested ${ageHours} h ago`);
  } else {
    console.log('  Snapshot: none yet — run `npm run harvest`.');
  }
  console.log();
}

main().catch((error) => {
  if (error.name === 'SessionExpiredError') {
    console.log('\n  Session: EXPIRED — run `npm run login` again.\n');
    process.exitCode = 2;
    return;
  }
  console.error('\n  Status check failed:', error.message, '\n');
  process.exitCode = 1;
});
