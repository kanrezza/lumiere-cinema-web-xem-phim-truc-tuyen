'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');

function setup(fetch) {
  const timers = new Map();
  let timerId = 0;
  const transport = loadFrontend('viewing/voice-transport.ts', {
    fetch, AbortController, URLSearchParams,
    document: {querySelector: () => ({value: 'csrf-token'}), cookie: ''},
    window: {
      setTimeout(callback) {const id = ++timerId; timers.set(id, callback); return id},
      clearTimeout(id) {timers.delete(id)},
    },
  });
  return {...transport, timers};
}

test('voice actions send session fields and CSRF without sharing cross-origin credentials', async () => {
  let request;
  const s = setup(async (url, options) => {
    request = {url, options};
    return {ok: true, redirected: false, json: async () => ({session: 'session-1'})};
  });
  const response = await s.postVoiceAction('/rooms/1/voice/action/', 'mic', {session: 'session-1', enabled: 'false'});
  assert.equal(response.session, 'session-1');
  assert.equal(request.options.method, 'POST');
  assert.equal(request.options.credentials, 'same-origin');
  assert.equal(request.options.cache, 'no-store');
  assert.equal(request.options.headers['X-CSRFToken'], 'csrf-token');
  assert.equal(request.options.body.get('action'), 'mic');
  assert.equal(request.options.body.get('session'), 'session-1');
  assert.equal(request.options.body.get('enabled'), 'false');
  assert.equal(s.timers.size, 0);
});

test('redirected voice responses preserve authorization failure instead of accepting a login page', async () => {
  const s = setup(async () => ({ok: true, redirected: true, status: 200, json: async () => {throw new Error('must not parse')}}));
  await assert.rejects(s.voiceRequest('/rooms/1/voice/'), error => error instanceof s.VoiceRequestError && error.status === 403);
  assert.equal(s.timers.size, 0);
  const forbidden = setup(async () => ({ok: false, redirected: false, status: 409}));
  await assert.rejects(forbidden.voiceRequest('/rooms/1/voice/'), error => error.status === 409);
  assert.equal(forbidden.timers.size, 0);
});

test('an expired voice request aborts its in-flight fetch and releases its timer', async () => {
  let signal;
  const s = setup((_url, options) => {
    signal = options.signal;
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')), {once: true}));
  });
  const request = s.voiceRequest('/rooms/1/voice/');
  assert.equal(signal.aborted, false);
  [...s.timers.values()][0]();
  await assert.rejects(request, /aborted/);
  assert.equal(signal.aborted, true);
  assert.equal(s.timers.size, 0);
});
