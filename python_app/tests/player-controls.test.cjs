'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

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
  function load(name) {vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static', name), 'utf8'), context, {filename: name});}
  return {load, video, wrap, range, actions, subtitleSelect, subtitleTracks, metadataTrack, counter, durationCounter, status, retry, doc, win, context, intervals};
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('paused +/-10 changes position and visible time immediately', () => {
  const env = environment(); env.load('player-controls.js');
  env.actions[2].fire('click'); assert.equal(env.video.currentTime, 33); assert.equal(env.counter.textContent, '0:33'); assert.equal(Number(env.range.value), 33); assert.equal(env.video.paused, true);
  env.actions[1].fire('click'); assert.equal(env.video.currentTime, 23); assert.equal(env.counter.textContent, '0:23');
});
test('duration labels absorb sub-millisecond HLS rounding without rounding ordinary fractions', () => {
  const env = environment(); env.video.duration = 19.999999; env.load('player-controls.js');
  assert.equal(env.durationCounter.textContent, '0:20');
  env.video.duration = 596.458; env.video.fire('durationchange'); assert.equal(env.durationCounter.textContent, '9:56');
});
test('rapid clicks accumulate even while the media getter still reports the old seek', () => {
  const env = environment({deferredSeek: true}); env.video.setActualTime(12); env.load('player-controls.js');
  env.actions[2].fire('click'); env.actions[2].fire('click'); env.actions[2].fire('click');
  assert.deepEqual(env.video.writes, [22, 32, 42]); assert.equal(env.counter.textContent, '0:42');
  env.video.setActualTime(42); env.video.fire('seeked'); assert.equal(env.counter.textContent, '0:42');
});
test('skip clamps both ends and respects separate seekable windows', () => {
  const env = environment(); env.load('player-controls.js');
  env.video.setActualTime(4); env.actions[1].fire('click'); assert.equal(env.video.currentTime, 0); env.video.fire('seeked');
  env.video.setActualTime(96); env.actions[2].fire('click'); assert.equal(env.video.currentTime, 100); env.video.fire('seeked');
  const windows = [[5, 20], [35, 50]];
  env.video.seekable = {length: 2, start: index => windows[index][0], end: index => windows[index][1]};
  env.video.setActualTime(18); env.actions[2].fire('click'); assert.equal(env.video.currentTime, 35); env.video.fire('seeked');
  env.actions[2].fire('click'); assert.equal(env.video.currentTime, 45); env.video.fire('seeked'); env.actions[2].fire('click'); assert.equal(env.video.currentTime, 50);
});
test('clamped no-op seek does not freeze the counter when no seeked event fires', () => {
  const env = environment(); env.video.setActualTime(0); env.load('player-controls.js');
  env.actions[1].fire('click'); assert.deepEqual(env.video.writes, []);
  env.video.setActualTime(3); env.video.fire('timeupdate'); assert.equal(env.counter.textContent, '0:03');
  env.actions[2].fire('click'); assert.equal(env.video.currentTime, 13); env.video.fire('seeked');
  env.video.setActualTime(100); env.actions[2].fire('click');
  env.video.setActualTime(96); env.video.fire('timeupdate'); assert.equal(env.counter.textContent, '1:36');
});
test('missing metadata, zero and unknown durations never assign NaN or seek', () => {
  for (const [readyState, duration] of [[0, 100], [1, 0], [1, NaN], [1, Infinity]]) {
    const env = environment(); env.video.readyState = readyState; env.video.duration = duration; env.load('player-controls.js'); env.actions[2].fire('click');
    assert.deepEqual(env.video.writes, []); assert.equal(env.video.currentTime, 23);
  }
});
test('timeline supports paused seek, and keyboard arrows ignore native form inputs', () => {
  const env = environment(); env.load('player-controls.js');
  env.range.value = '72'; env.range.fire('input'); assert.equal(env.video.currentTime, 72); assert.equal(env.counter.textContent, '1:12'); env.video.fire('seeked');
  const event = env.wrap.fire('keydown', {key: 'ArrowLeft', target: env.actions[0]}); assert.equal(event.defaultPrevented, true); assert.equal(env.video.currentTime, 62); env.video.fire('seeked');
  const inputEvent = env.wrap.fire('keydown', {key: 'ArrowRight', target: env.range}); assert.equal(inputEvent.defaultPrevented, false); assert.equal(env.video.currentTime, 62);
  env.wrap.fire('keydown', {key: 'ArrowRight', target: env.actions[0], ctrlKey: true}); assert.equal(env.video.currentTime, 62);
});
test('watch-party guests cannot seek locally and captions remain independent', () => {
  const env = environment({guest: true}); env.load('player-controls.js'); env.actions[2].fire('click');
  assert.deepEqual(env.video.writes, []); assert.equal(env.actions[2].disabled, true); assert.equal(env.range.disabled, true);
  env.subtitleSelect.value = '1'; env.subtitleSelect.fire('change'); assert.equal(env.subtitleTracks[1].track.mode, 'showing');
});
test('caption switch shows only the chosen DOM subtitle track and survives source metadata refresh', () => {
  const env = environment(); env.load('player-controls.js');
  assert.equal(env.subtitleSelect.value, 'off'); assert.equal(env.metadataTrack.mode, 'hidden');
  env.subtitleSelect.value = '1'; env.subtitleSelect.fire('change'); assert.equal(env.subtitleTracks[1].track.mode, 'showing'); assert.equal(env.subtitleTracks[0].track.mode, 'disabled');
  env.video.fire('emptied'); env.video.fire('loadedmetadata'); assert.equal(env.subtitleTracks[1].track.mode, 'showing'); assert.equal(env.subtitleSelect.value, '1');
  env.subtitleSelect.value = 'off'; env.subtitleSelect.fire('change'); assert.equal(env.subtitleTracks[1].track.mode, 'disabled'); assert.equal(env.metadataTrack.mode, 'hidden');
});
test('player works when no subtitle selector exists', () => {
  const env = environment({subtitles: false}); env.load('player-controls.js'); env.actions[2].fire('click'); assert.equal(env.video.currentTime, 33);
});
test('source refresh preserves a seek made while the ticket request is pending', async () => {
  const env = environment(); let resolveTicket;
  env.context.postForm = () => new Promise(resolve => {resolveTicket = resolve;});
  class Hls {static isSupported() {return true;} static Events = {ERROR: 'error'}; loadSource() {} attachMedia() {} on() {} destroy() {env.video.fire('emptied');}}
  env.context.Hls = Hls; env.win.Hls = Hls;
  env.load('player.js'); resolveTicket({url: '/first.m3u8'}); await tick(); env.video.fire('loadedmetadata'); assert.equal(env.video.currentTime, 14);
  env.video.setActualTime(40); env.intervals.find(interval => interval.delay === 480000).callback();
  env.video.setActualTime(60); env.video.dispatchEvent(new env.context.CustomEvent('lumiere:seek', {detail: {position: 60}}));
  resolveTicket({url: '/refresh.m3u8'}); await tick(); env.video.fire('loadedmetadata'); assert.equal(env.video.currentTime, 60); assert.equal(env.video.dataset.loading, 'false');
});
test('retry removes stale metadata callbacks from failed sources', async () => {
  const env = environment(); let request = 0; const handlers = [];
  env.context.postForm = async () => ({url: `/source-${++request}.m3u8`});
  class Hls {static isSupported() {return true;} static Events = {ERROR: 'error'}; loadSource() {} attachMedia() {} on(event, callback) {handlers.push(callback);} destroy() {env.video.fire('emptied');}}
  env.context.Hls = Hls; env.win.Hls = Hls;
  env.load('player.js'); await tick(); handlers[0]('error', {fatal: true}); assert.equal(env.video.dataset.loading, 'false');
  env.retry.fire('click'); await tick(); env.video.writes.length = 0; env.video.fire('loadedmetadata'); assert.deepEqual(env.video.writes, [14]);
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
  env.load('room.js');
  env.video.paused = false; env.video.readyState = 1;
  env.video.setActualTime(10); env.video.fire('seeked'); env.video.setActualTime(20); env.video.fire('seeked');
  env.video.paused = true; env.video.setActualTime(30); env.video.fire('seeked');
  assert.deepEqual(sends.map(item => item.position), [10]); assert.equal(sends[0].playing, true);
  completions[0]({ok: true}); await tick();
  assert.deepEqual(sends.map(item => item.position), [10, 30]);
  completions[1]({ok: true}); await tick();
  assert.equal(sends[1].playing, false);
});


test('loaded caption cues sit above custom controls and retain native timing', () => {
  const env = environment(); env.load('player-controls.js');
  const cue = {line: 'auto', snapToLines: false, startTime: 2, endTime: 6, text: 'Nội dung phụ đề'};
  env.subtitleTracks[0].track.cues = [cue]; env.subtitleTracks[0].fire('load');
  assert.equal(cue.line, -5); assert.equal(cue.snapToLines, true); assert.equal(cue.startTime, 2); assert.equal(cue.endTime, 6); assert.equal(cue.text, 'Nội dung phụ đề');
  env.video.fire('loadedmetadata'); assert.equal(cue.line, -5);
  env.wrap.clientWidth = 320; env.win.fire('resize'); assert.equal(cue.line, -2);
  env.wrap.clientWidth = 1200; env.doc.fire('fullscreenchange'); assert.equal(cue.line, -5);
});

test('a pause while awaiting a new HLS ticket is preserved', async () => {
  const env = environment(); let resolveTicket;
  env.video.paused = false;
  env.context.postForm = () => new Promise(resolve => {resolveTicket = resolve;});
  class Hls {static isSupported() {return true;} static Events = {ERROR: 'error'}; loadSource() {} attachMedia() {} on() {} destroy() {env.video.fire('emptied');}}
  env.context.Hls = Hls; env.win.Hls = Hls;
  env.load('player.js'); env.video.pause(); resolveTicket({url: '/source.m3u8'}); await tick(); env.video.fire('loadedmetadata');
  assert.equal(env.video.paused, true); assert.equal(env.video.dataset.loading, 'false');
});
