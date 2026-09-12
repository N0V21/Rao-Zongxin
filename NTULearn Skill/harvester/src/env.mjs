/**
 * Environment bootstrap. Import this FIRST, before `playwright`, so the bundled
 * browser directory resolves no matter how the script is invoked (npm script,
 * direct `node`, or from a different cwd).
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const WORKSPACE_ROOT = path.resolve(PKG_ROOT, '..');

// Keep the ~150MB browser download inside the workspace instead of ~/Library,
// so the whole setup stays self-contained and disposable.
process.env.PLAYWRIGHT_BROWSERS_PATH ??= path.join(WORKSPACE_ROOT, '.browsers');
