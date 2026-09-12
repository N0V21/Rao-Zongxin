/**
 * NTULearn authenticated HTTP client.
 *
 * Reuses the browser session captured by `login.mjs` (a Playwright storageState
 * file) and exposes a small JSON fetch wrapper pointed at the Blackboard Learn
 * origin. No credentials are ever read or stored here — only session cookies.
 */

import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const ORIGIN = 'https://ntulearn.ntu.edu.sg';
export const STATE_PATH = path.join(ROOT, '.auth', 'state.json');
export const PROFILE_DIR = path.join(ROOT, '.auth', 'profile');

/** Thrown when the saved session is missing or no longer accepted by the server. */
export class SessionExpiredError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SessionExpiredError';
  }
}

/** Read the saved Playwright storageState, or throw if the user never logged in. */
export async function loadStorageState() {
  if (!existsSync(STATE_PATH)) {
    throw new SessionExpiredError(
      `No saved session at ${STATE_PATH}. Run \`npm run login\` first.`,
    );
  }
  return JSON.parse(await readFile(STATE_PATH, 'utf8'));
}

/**
 * Minimal cookie-aware JSON client for Blackboard.
 *
 * Blackboard Learn SaaS accepts the browser's session cookie on its public REST
 * API for the logged-in user, so we replay the captured cookies with plain
 * fetch rather than paying for a browser on every request.
 */
export class BlackboardClient {
  /** @param {{cookies: Array<{name: string, value: string, domain: string}>}} storageState */
  constructor(storageState, { origin = ORIGIN, throttleMs = 120 } = {}) {
    this.origin = origin;
    this.throttleMs = throttleMs;
    this.cookieHeader = storageState.cookies
      .filter((c) => origin.includes(c.domain.replace(/^\./, '')) || c.domain.startsWith('.'))
      .map((c) => `${c.name}=${c.value}`)
      .join('; ');
    this.lastRequestAt = 0;
    /** Every URL we actually touched, so the harvester can cite its sources. */
    this.requestLog = [];
  }

  /** Sleep just enough to keep us polite between calls. */
  async #throttle() {
    const wait = this.throttleMs - (Date.now() - this.lastRequestAt);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    this.lastRequestAt = Date.now();
  }

  /**
   * Perform a JSON request against the Blackboard origin.
   *
   * @param {string} url absolute URL, or a path resolved against the origin
   * @param {{method?: string, body?: unknown, headers?: Record<string,string>, raw?: boolean}} [options]
   * @returns {Promise<any>} parsed JSON, or the raw Response when `raw` is set
   */
  async request(url, options = {}) {
    const { method = 'GET', body, headers = {}, raw = false } = options;
    const target = url.startsWith('http') ? url : `${this.origin}${url}`;
    await this.#throttle();

    const response = await fetch(target, {
      method,
      redirect: 'follow',
      headers: {
        accept: 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        cookie: this.cookieHeader,
        'x-bb-router': 'BbRouter',
        ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
        ...headers,
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });

    this.requestLog.push({ url: target, method, status: response.status });

    // An expired session shows up as a 401, or as a redirect into the SAML/Entra
    // login flow that lands on an HTML page instead of JSON. A bare 403 is a
    // normal authorization answer for an endpoint this account may not use, so
    // it must NOT be mistaken for an expired session.
    const finalUrl = response.url || target;
    if (
      response.status === 401 ||
      !finalUrl.startsWith(this.origin) ||
      /auth-saml|login\.microsoftonline/.test(finalUrl)
    ) {
      throw new SessionExpiredError(
        `Session rejected for ${target}. Re-run \`npm run login\`.`,
      );
    }
    if (raw) return response;
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      const error = new Error(`HTTP ${response.status} for ${target}: ${text.slice(0, 300)}`);
      error.status = response.status;
      throw error;
    }

    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  /** GET JSON. */
  get(url, options) {
    return this.request(url, { ...options, method: 'GET' });
  }

  /**
   * The current user, used as both a session check and the userId we need for
   * membership lookups.
   */
  me() {
    return this.get('/learn/api/public/v1/users/me');
  }
}

/** Build a client from the saved session, throwing a friendly error if absent. */
export async function createClient(options) {
  return new BlackboardClient(await loadStorageState(), options);
}
