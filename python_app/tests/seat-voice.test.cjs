'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');

class Target {
  constructor() { this.listeners = new Map(); }
  addEventListener(name, listener, options = {}) {
    const entries = this.listeners.get(name) || [];
    entries.push(listener);
    this.listeners.set(name, entries);
    options.signal?.addEventListener('abort', () => this.removeEventListener(name, listener), {once: true});
  }
  removeEventListener(name, listener) {
    this.listeners.set(name, (this.listeners.get(name) || []).filter(entry => entry !== listener));
  }
  dispatchEvent(event) {
    for (const listener of [...(this.listeners.get(event.type) || [])]) listener(event);
    return true;
  }
}
class FakeElement extends Target {
  constructor() { super(); this.dataset = {}; this.disabled = false; }
  closest() { return null; }
  setAttribute(name, value) { this[name] = value; }
}
class FakeEvent {
  constructor(type, options = {}) { this.type = type; Object.assign(this, options); }
}
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup({captureError, deferCapture = false, deferJoin = false} = {}) {
  const timers = new Map(), requests = [], captured = [], states = [];
  const room = new FakeElement();
  room.dataset = {voice: '/rooms/fixture/voice/', voiceAction: '/rooms/fixture/voice/action/', user: '2', hostUser: '1', host: 'false'};
  const join = new FakeElement(), mic = new FakeElement(), play = new FakeElement(), audio = new FakeElement();
  room.querySelector = selector => ({
    '[data-voice-join]': join, '[data-voice-mic]': mic, '[data-voice-play]': play,
    '[data-voice-audio]': audio,
  })[selector] || null;
  const document = new Target();
  document.querySelector = () => ({value: 'test-csrf'});
  document.cookie = ''; document.hidden = false;
  const window = new Target();
  let nextTimer = 0, serverSession = null, hostMuted = false, serverMic = false;
  let pendingCapture, pendingJoin;
  window.isSecureContext = true;
  window.RTCPeerConnection = function () {};
  window.setTimeout = (callback, delay) => { const id = ++nextTimer; timers.set(id, {callback, delay}); return id; };
  window.clearTimeout = id => timers.delete(id);
  window.setInterval = window.setTimeout;
  window.clearInterval = window.clearTimeout;
  const track = new Target();
  Object.assign(track, {kind: 'audio', readyState: 'live', enabled: true, muted: false, stops: 0});
  track.stop = () => { track.stops++; track.readyState = 'ended'; track.enabled = false; };
  const stream = {getAudioTracks: () => [track], getTracks: () => [track]};
  const navigator = {mediaDevices: {getUserMedia(options) {
    captured.push(options);
    if (captureError) return Promise.reject(captureError);
    if (deferCapture) return new Promise(resolve => {pendingCapture = () => resolve(stream)});
    return Promise.resolve(stream);
  }}, sendBeacon() {return true}};
  const fetch = async (url, options = {}) => {
    const fields = options.body ? Object.fromEntries(options.body) : {};
    requests.push({url: String(url), method: options.method || 'GET', fields});
    const reply = value => ({ok: true, redirected: false, status: 200, json: async () => value});
    if (fields.action === 'join') {
      const complete = () => {serverSession = 'joined-session'; serverMic = false; return reply({session: serverSession})};
      if (deferJoin) return new Promise(resolve => {pendingJoin = () => resolve(complete())});
      return complete();
    }
    if (fields.action === 'mic') {
      if (fields.enabled === 'true' && hostMuted) return {ok: false, redirected: false, status: 403};
      serverMic = fields.enabled === 'true';
      return reply({ok: true});
    }
    if (fields.action === 'leave') {serverSession = null; serverMic = false; return reply({ok: true});}
    return reply({self: {user_id: 2, voice_session: serverSession, host_muted: hostMuted, mic_on: serverMic}, peers: [], signals: [], ice_servers: []});
  };
  room.addEventListener('lumiere:voice-state', event => states.push(event.detail));
  const {initVoice} = loadFrontend('viewing/voice-driver.ts', {
    window, document, navigator, fetch, URL, URLSearchParams, AbortController,
    location: {href: 'http://localhost/rooms/fixture/'}, Element: FakeElement,
    HTMLElement: FakeElement, HTMLButtonElement: FakeElement,
    Event: FakeEvent, CustomEvent: FakeEvent,
    performance: {now: () => 0},
  });
  initVoice(room);
  async function settle() {
    for (let turn = 0; turn < 12; turn++) {
      await flush();
      const immediate = [...timers].filter(([, timer]) => timer.delay === 0);
      if (!immediate.length) { await flush(); break; }
      for (const [id, timer] of immediate) {timers.delete(id); timer.callback();}
    }
  }
  async function poll() {
    await settle();
    const next = [...timers].filter(([, timer]) => timer.delay <= 2500).sort((a, b) => a[1].delay - b[1].delay)[0];
    assert.ok(next, 'voice polling should remain scheduled');
    timers.delete(next[0]); next[1].callback();
    await settle();
  }
  return {
    room, requests, captured, states, track, settle, poll,
    current: () => states.at(-1),
    avatar() { room.dispatchEvent(new FakeEvent('lumiere:voice-toggle-mic')); },
    setHostMuted(value) {hostMuted = value; if (value) serverMic = false;},
    completeCapture() {assert.ok(pendingCapture); pendingCapture();},
    completeJoin() {assert.ok(pendingJoin); pendingJoin();},
    stop() {document.dispatchEvent(new FakeEvent('lumiere:stop'));},
  };
}

test('entering a room automatically listens with no microphone capture or enable command', async () => {
  const s = setup();
  await s.settle();
  assert.equal(s.requests.filter(row => row.fields.action === 'join').length, 1);
  assert.equal(s.captured.length, 0);
  assert.equal(s.current().listening, true);
  assert.equal(s.current().microphone, false);
  assert.equal(s.requests.some(row => row.fields.action === 'mic' && row.fields.enabled === 'true'), false);
  s.stop();
});

test('own seat activation requests the mic immediately and a second activation switches it off', async () => {
  const s = setup();
  await s.settle();
  s.avatar();
  assert.equal(s.captured.length, 1, 'capture must start in the avatar activation call stack');
  await s.settle();
  assert.equal(s.current().microphone, true);
  assert.equal(s.track.enabled, true);
  s.avatar();
  assert.equal(s.track.stops, 1);
  await s.settle();
  assert.equal(s.current().microphone, false);
  assert.equal(s.requests.filter(row => row.fields.action === 'mic').at(-1).fields.enabled, 'false');
  assert.equal(s.captured.length, 1);
  s.stop();
});

test('a host mic lock silences the local track and allowing speech never opens it automatically', async () => {
  const s = setup();
  await s.settle();
  s.avatar(); await s.settle();
  assert.equal(s.current().microphone, true);
  s.setHostMuted(true); await s.poll();
  assert.equal(s.track.stops, 1);
  assert.equal(s.current().microphone, false);
  assert.equal(s.current().micState, 'muted');
  s.avatar(); await s.settle();
  assert.equal(s.captured.length, 1, 'locked avatar must not request microphone permission');
  s.setHostMuted(false); await s.poll();
  assert.equal(s.current().microphone, false);
  assert.equal(s.captured.length, 1, 'unlocking only allows the user to opt in again');
  s.stop();
});

test('denied microphone permission keeps listening and never enables a ghost microphone', async () => {
  const failure = new Error('Permission denied'); failure.name = 'NotAllowedError';
  const s = setup({captureError: failure});
  await s.settle();
  s.avatar(); await s.settle();
  assert.equal(s.current().listening, true);
  assert.equal(s.current().microphone, false);
  assert.equal(s.current().micDisabled, false);
  assert.equal(s.requests.some(row => row.fields.action === 'mic' && row.fields.enabled === 'true'), false);
  s.stop();
});

test('a host lock received while the permission prompt is pending cancels the eventual track', async () => {
  const s = setup({deferCapture: true});
  await s.settle();
  s.avatar();
  assert.equal(s.captured.length, 1);
  s.setHostMuted(true); await s.poll();
  s.completeCapture(); await s.settle();
  assert.equal(s.track.stops, 1);
  assert.equal(s.current().microphone, false);
  assert.equal(s.requests.some(row => row.fields.action === 'mic' && row.fields.enabled === 'true'), false);
  s.stop();
});

test('avatar activation during the initial join preserves capture intent without a second join', async () => {
  const s = setup({deferJoin: true});
  await s.settle();
  assert.equal(s.requests.filter(row => row.fields.action === 'join').length, 1);
  s.avatar();
  assert.equal(s.captured.length, 1);
  s.completeJoin(); await s.settle();
  assert.equal(s.requests.filter(row => row.fields.action === 'join').length, 1);
  assert.equal(s.current().microphone, true);
  s.stop();
});
