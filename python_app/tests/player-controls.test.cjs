'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');
const {formatTime, seekPosition} = loadFrontend('viewing/seek.ts');

function windows(...ranges) {
  return {length: ranges.length, start: index => ranges[index][0], end: index => ranges[index][1]};
}

test('duration formatting absorbs HLS sub-millisecond rounding', () => {
  assert.equal(formatTime(19.999999), '0:20');
  assert.equal(formatTime(596.458), '9:56');
});

test('seek targets clamp to video bounds and to the nearest HLS boundary', () => {
  assert.equal(seekPosition(-10, 30, windows()), 0);
  assert.equal(seekPosition(50, 30, windows()), 30);
  assert.equal(seekPosition(13, 30, windows([0, 10], [20, 30])), 10);
  assert.equal(seekPosition(16, 30, windows([0, 10], [20, 30])), 20);
  assert.equal(seekPosition(22, 30, windows([0, 10], [20, 30])), 22);
});

test('seek rejects non-finite targets and unavailable metadata', () => {
  for (const duration of [0, NaN, Infinity]) assert.equal(seekPosition(10, duration, windows()), undefined);
  assert.equal(seekPosition(NaN, 30, windows()), undefined);
});

class Element {
  constructor(tag = 'div') {this.tag = tag; this.listeners = new Map(); this.attributes = {}; this.dataset = {}; this.value = ''; this.hidden = false; this.disabled = false; this.textContent = ''; this.classList = {toggle() {}};}
  addEventListener(name, fn, options = {}) {const entries = this.listeners.get(name) || []; entries.push({fn, once: options.once}); this.listeners.set(name, entries);}
  removeEventListener(name, fn) {this.listeners.set(name, (this.listeners.get(name) || []).filter(entry => entry.fn !== fn));}
  dispatchEvent(event) {event.target ||= this; for (const entry of [...(this.listeners.get(event.type) || [])]) {if (entry.once) this.removeEventListener(event.type, entry.fn); entry.fn(event);} return !event.defaultPrevented;}
  fire(type, extra = {}) {const event = {type, defaultPrevented: false, preventDefault() {this.defaultPrevented = true;}, ...extra}; this.dispatchEvent(event); return event;}
  setAttribute(name, value) {this.attributes[name] = value;}
  removeAttribute(name) {delete this.attributes[name];}
  closest(selector) {return selector.includes('input, select') && ['input', 'select', 'textarea'].includes(this.tag) ? this : null;}
}
class Tracks extends Array {
  addEventListener(name, fn) {this.listener = fn;}
}
function environment({guest = false, deferredSeek = false, subtitles = true} = {}) {
  const wrap = new Element(), video = new Element('video'), controls = new Element(), center = new Element('button');
  const range = new Element('input'), volume = new Element('input'), subtitleSelect = new Element('select');
  const status = new Element(), retry = new Element('button'), doc = new Element(), win = new Element();
  const room = guest ? new Element() : null;
  if (room) room.dataset.host = 'false';
  const actions = ['play', 'back', 'forward', 'mute', 'fullscreen'].map(action => {const button = new Element('button'); button.dataset.playerAction = action; return button;});
  const counter = new Element(), durationCounter = new Element(), quality = new Element();
  const query = new Map([['.player-controls', controls], ['.player-center', center], ['.player-range', range], ['.player-volume', volume], ['.player-toggle', actions[0]], ['[data-player-action=mute]', actions[3]], ['[data-player-action=fullscreen]', actions[4]], ['[data-player-time]', counter], ['[data-player-duration]', durationCounter], ['[data-player-quality]', quality], ['.player-subtitles', subtitles ? subtitleSelect : null]]);
  wrap.querySelector = selector => query.get(selector) ?? null;
  wrap.querySelectorAll = () => [center, ...actions];
  video.closest = () => wrap;
  video.duration = 100; video.readyState = 4; video.videoHeight = 720; video.paused = true; video.ended = false;
  video.volume = 1; video.muted = false; video.controls = true;
  let position = 23;
  video.writes = [];
  Object.defineProperty(video, 'currentTime', {get: () => position, set: value => {video.writes.push(value); if (!deferredSeek) position = value;}});
  video.setActualTime = value => {position = value;};
  video.seekable = {length: 0};
  const subtitleTracks = [new Element('track'), new Element('track')];
  subtitleTracks.forEach(element => {element.track = {mode: 'disabled', cues: []};});
  const metadataTrack = {mode: 'hidden'};
  video.textTracks = new Tracks(metadataTrack, ...subtitleTracks.map(element => element.track));
  video.querySelectorAll = () => subtitleTracks;
  video.play = async () => {video.paused = false; video.fire('play');};
  video.pause = () => {video.paused = true; video.fire('pause');};
  video.load = () => {};
  video.dataset = {ticket: '/ticket', progress: '/progress', position: '14', loading: 'false'};
  video.canPlayType = () => '';
  doc.getElementById = id => ({player: video, 'player-status': status, 'retry-player': retry, room}[id] ?? null);
  const intervals = [];
  const context = {document: doc, window: win, CustomEvent: class {constructor(type, options = {}) {this.type = type; this.detail = options.detail;}}, Event: class {constructor(type) {this.type = type;}}, navigator: {sendBeacon() {}}, URLSearchParams, setInterval: (callback, delay) => intervals.push({callback, delay}), console};
  doc.querySelector = () => ({value: 'token'});
  win.setInterval = context.setInterval;
  win.clearInterval = () => {};
  function load(name) {
    const original = context.fetch;
    context.fetch = async (url, options) => {
      if (options?.method !== 'POST') return original?.(url, options);
      const fields = Object.fromEntries(options.body);
      if ('position' in fields) fields.position = Number(fields.position);
      if ('playing' in fields) fields.playing = fields.playing === 'true';
      const value = await context.postForm(url, fields);
      return {ok: true, redirected: false, json: async () => value};
    };
    if (name === 'playback') return loadFrontend('viewing/playback.ts', context).initPlayback(video);
    else {
      const room = doc.getElementById('room');
      const form = doc.getElementById('chat-form');
      form.querySelector = selector => new Element(selector.startsWith('input') ? 'input' : 'button');
      room.querySelector = selector => doc.getElementById(selector.slice(1));
      loadFrontend('viewing/room-driver.ts', context).initRoom(room, video);
    }
  }
  return {load, video, wrap, range, actions, subtitleSelect, subtitleTracks, metadataTrack, counter, durationCounter, status, retry, doc, win, context, intervals};
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('source refresh preserves a seek made while the ticket request is pending', async () => {
  const env = environment(); let resolveTicket;
  env.context.postForm = () => new Promise(resolve => {resolveTicket = resolve;});
  class Hls {static isSupported() {return true;} static Events = {ERROR: 'error'}; loadSource() {} attachMedia() {} on() {} destroy() {env.video.fire('emptied');}}
  env.context.Hls = Hls; env.win.Hls = Hls;
  env.load('playback'); resolveTicket({url: '/first.m3u8'}); await tick(); env.video.fire('loadedmetadata'); assert.equal(env.video.currentTime, 14);
  env.video.setActualTime(40); env.intervals.find(interval => interval.delay === 480000).callback();
  env.video.setActualTime(60); env.video.dispatchEvent(new env.context.CustomEvent('lumiere:seek', {detail: {position: 60}}));
  resolveTicket({url: '/refresh.m3u8'}); await tick(); env.video.fire('loadedmetadata'); assert.equal(env.video.currentTime, 60); assert.equal(env.video.dataset.loading, 'false');
});
test('loading a resume position without playing does not write progress', async () => {
  const env = environment(), saves = [];
  env.context.postForm = async (url, data) => {
    if (url === '/progress') saves.push(data.position);
    return {url: '/demo.m3u8'};
  };
  env.video.canPlayType = () => 'maybe';
  env.context.csrfToken = () => 'token';
  env.context.navigator.sendBeacon = (_url, fields) => saves.push(Number(fields.get('position')));
  env.load('playback');
  await tick();
  env.video.fire('loadedmetadata');
  env.video.fire('pause');
  env.win.fire('pagehide');
  assert.deepEqual(saves, []);
  env.video.fire('playing');
  env.video.setActualTime(18);
  env.video.fire('pause');
  env.win.fire('pagehide');
  assert.deepEqual(saves, [18, 18]);
});

test('retry removes stale metadata callbacks from failed sources', async () => {
  const env = environment(); let request = 0; const handlers = [];
  env.context.postForm = async () => ({url: `/source-${++request}.m3u8`});
  class Hls {static isSupported() {return true;} static Events = {ERROR: 'error'}; loadSource() {} attachMedia() {} on(event, callback) {handlers.push(callback);} destroy() {env.video.fire('emptied');}}
  env.context.Hls = Hls; env.win.Hls = Hls;
  env.load('playback'); await tick(); handlers[0]('error', {fatal: true}); assert.equal(env.video.dataset.loading, 'false');
  env.retry.fire('click'); await tick(); env.video.writes.length = 0; env.video.fire('loadedmetadata'); assert.deepEqual(env.video.writes, [14]);
});

test('switching a room film disposes the old stream and saves its final progress once', async () => {
  const env = environment(), saves = [], cleared = [];
  let destroyed = 0, requests = 0;
  env.win.clearInterval = id => cleared.push(id);
  env.context.postForm = async (url, data) => {
    if (url === '/progress') saves.push(data.position);
    else requests++;
    return {url: '/old-film.m3u8'};
  };
  class Hls {
    static isSupported() {return true;}
    static Events = {ERROR: 'error'};
    loadSource() {} attachMedia() {} on() {}
    destroy() {destroyed++;}
  }
  env.win.Hls = Hls;
  const dispose = env.load('playback');
  await tick();
  env.video.fire('loadedmetadata');
  env.video.fire('playing');
  env.video.setActualTime(42);
  dispose();
  await tick();
  env.video.fire('pause');
  env.retry.fire('click');
  env.win.fire('pagehide');
  env.intervals.forEach(interval => interval.callback());
  await tick();
  assert.deepEqual(saves, [42]);
  assert.equal(destroyed, 1);
  assert.equal(requests, 1);
  assert.equal(cleared.length, 2);
});

test('a ticket returned after switching films cannot start the removed player', async () => {
  const env = environment();
  let resolveTicket, loaded = 0;
  env.context.postForm = () => new Promise(resolve => {resolveTicket = resolve;});
  class Hls {
    static isSupported() {return true;}
    static Events = {ERROR: 'error'};
    loadSource() {loaded++;} attachMedia() {} on() {} destroy() {}
  }
  env.win.Hls = Hls;
  const dispose = env.load('playback');
  dispose();
  resolveTicket({url: '/late-old-film.m3u8'});
  await tick();
  assert.equal(loaded, 0);
  assert.equal(env.video.src, undefined);
});

test('watch-party host sync serializes requests and sends the latest queued seek', async () => {
  const env = environment(); const room = new Element(), status = new Element(), chat = new Element(), members = new Element();
  room.dataset = {host: 'true', state: '/room-state', user: '1'};
  const controls = new Map([['room', room], ['room-status', status], ['copy-invite', new Element('button')], ['close-room', new Element('button')], ['chat-form', new Element('form')], ['chat-messages', chat], ['members', members]]);
  const originalGet = env.doc.getElementById;
  env.doc.getElementById = id => controls.get(id) || originalGet(id);
  env.context.fetch = () => new Promise(() => {});
  env.context.setTimeout = () => {};
  const sends = [], completions = [];
  env.context.postForm = (_url, data) => {sends.push({...data}); return new Promise(resolve => completions.push(resolve));};
  env.load('room');
  env.video.paused = false; env.video.readyState = 1;
  env.video.setActualTime(10); env.video.fire('seeked'); env.video.setActualTime(20); env.video.fire('seeked');
  env.video.paused = true; env.video.setActualTime(30); env.video.fire('seeked');
  assert.deepEqual(sends.map(item => item.position), [10]); assert.equal(sends[0].playing, true);
  completions[0]({ok: true}); await tick();
  assert.deepEqual(sends.map(item => item.position), [10, 30]);
  completions[1]({ok: true}); await tick();
  assert.equal(sends[1].playing, false);
});

test('a pause while awaiting a new HLS ticket is preserved', async () => {
  const env = environment(); let resolveTicket;
  env.video.paused = false;
  env.context.postForm = () => new Promise(resolve => {resolveTicket = resolve;});
  class Hls {static isSupported() {return true;} static Events = {ERROR: 'error'}; loadSource() {} attachMedia() {} on() {} destroy() {env.video.fire('emptied');}}
  env.context.Hls = Hls; env.win.Hls = Hls;
  env.load('playback'); env.video.pause(); resolveTicket({url: '/source.m3u8'}); await tick(); env.video.fire('loadedmetadata');
  assert.equal(env.video.paused, true); assert.equal(env.video.dataset.loading, 'false');
});

test('changing HLS quality keeps the current position and playing state', async () => {
  const env = environment(), sources = [];
  const qualities = [720, 1080].map(height => ({height, label: `${height}p`, url: `/q${height}.m3u8`}));
  env.context.postForm = async () => ({url: '/auto.m3u8', qualities, max_quality: 1440});
  class Hls {
    static isSupported() {return true;}
    static Events = {ERROR: 'error'};
    loadSource(url) {sources.push(url);}
    attachMedia() {} on() {}
    destroy() {env.video.fire('emptied');}
  }
  env.win.Hls = Hls;
  env.load('playback'); await tick(); env.video.fire('loadedmetadata');
  env.video.setActualTime(42); env.video.paused = false;
  env.video.dispatchEvent(new env.context.CustomEvent('lumiere:quality-select', {detail: {height: 1080}}));
  await tick(); env.video.fire('loadedmetadata');
  assert.deepEqual(sources, ['/auto.m3u8', '/q1080.m3u8']);
  assert.equal(env.video.currentTime, 42);
  assert.equal(env.video.paused, false);
  assert.equal(env.video.dataset.loading, 'false');
});

test('quality choices use the ticket list and native HLS preserves a paused position', async () => {
  const env = environment(); let requests = 0;
  env.video.canPlayType = () => 'maybe';
  env.context.postForm = async () => ({url: `/auto-${++requests}.m3u8`, qualities: [{height: 720, label: '720p', url: `/q720-${requests}.m3u8`}], max_quality: 720});
  env.load('playback'); await tick(); env.video.fire('loadedmetadata');
  env.video.setActualTime(37);
  env.video.dispatchEvent(new env.context.CustomEvent('lumiere:quality-select', {detail: {height: 1080}}));
  await tick();
  assert.equal(requests, 1);
  env.video.dispatchEvent(new env.context.CustomEvent('lumiere:quality-select', {detail: {height: 720}}));
  await tick(); env.video.fire('loadedmetadata');
  assert.equal(env.video.src, '/q720-2.m3u8');
  assert.equal(env.video.currentTime, 37);
  assert.equal(env.video.paused, true);
});

test('renewing a ticket drops an expired VIP quality and updates the picker', async () => {
  const env = environment(), states = []; let vip = true;
  env.video.canPlayType = () => 'maybe';
  env.video.addEventListener('lumiere:qualities', event => states.push(event.detail));
  env.context.postForm = async () => ({url: '/auto.m3u8', qualities: (vip ? [720, 1080] : [720]).map(height => ({height, label: `${height}p`, url: `/q${height}.m3u8`})), max_quality: vip ? 1440 : 720});
  env.load('playback'); await tick(); env.video.fire('loadedmetadata');
  env.video.dispatchEvent(new env.context.CustomEvent('lumiere:quality-select', {detail: {height: 1080}}));
  await tick(); env.video.fire('loadedmetadata');
  assert.equal(env.video.src, '/q1080.m3u8');
  vip = false;
  env.intervals.find(interval => interval.delay === 480000).callback();
  await tick(); env.video.fire('loadedmetadata');
  assert.equal(env.video.src, '/auto.m3u8');
  assert.equal(states.at(-1).selected, 'auto');
  assert.equal(states.at(-1).maxQuality, 720);
  assert.deepEqual(Array.from(states.at(-1).qualities, quality => quality.height), [720]);
});

test('premiere playback starts without a personal progress endpoint and never saves watch progress', async () => {
  const env = environment(), requests = [];
  env.video.canPlayType = () => 'maybe';
  env.video.dataset.premiere = 'true';
  delete env.video.dataset.progress;
  env.context.postForm = async url => {requests.push(url); return {url: '/premiere.m3u8'};};
  const dispose = env.load('playback');
  await tick(); env.video.fire('loadedmetadata'); env.video.fire('playing');
  env.video.setActualTime(30); env.video.fire('pause'); env.win.fire('pagehide'); dispose();
  await tick();
  assert.deepEqual(requests, ['/ticket']);
});
