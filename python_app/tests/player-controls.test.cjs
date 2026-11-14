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
test('subtitle preference follows the language to another episode on the same account', () => {
  const settings = new Map();
  const storage = {getItem: key => settings.get(key), setItem: (key, value) => settings.set(key, value)};
  function player(viewer, languages) {
    const env = environment();
    env.wrap.dataset.viewer = viewer;
    env.win.localStorage = storage;
    languages.forEach((language, index) => {env.subtitleTracks[index].srclang = language;});
    env.load('player-controls.js');
    return env;
  }
  const first = player('4', ['en', 'vi']);
  first.subtitleSelect.value = '1';
  first.subtitleSelect.fire('change');
  assert.equal(player('4', ['en', 'fr']).subtitleSelect.value, 'off');
  const second = player('4', ['vi', 'en']);
  assert.equal(second.subtitleSelect.value, '0');
  assert.equal(second.subtitleTracks[0].track.mode, 'showing');
  assert.equal(player('5', ['vi', 'en']).subtitleSelect.value, 'off');
  second.subtitleSelect.value = 'off';
  second.subtitleSelect.fire('change');
  assert.equal(player('4', ['vi', 'en']).subtitleSelect.value, 'off');
});
test('player works when no subtitle selector exists', () => {
  const env = environment({subtitles: false}); env.load('player-controls.js'); env.actions[2].fire('click'); assert.equal(env.video.currentTime, 33);
});
test('a generated or translated caption track can be selected without reloading the movie', () => {
  const env = environment(); env.load('player-controls.js');
  const translated = new Element('track');
  translated.track = {mode: 'disabled', cues: [{line: 'auto', snapToLines: false, text: 'Xin chào'}]};
  env.subtitleTracks.push(translated);
  env.video.fire('lumiere:captions-changed', {detail: {selected: '2'}});
  assert.equal(translated.track.mode, 'showing');
  assert.equal(env.subtitleSelect.value, '2');
  assert.equal(env.subtitleTracks[0].track.mode, 'disabled');
  translated.fire('load'); assert.equal(translated.track.cues[0].line, -5);
  translated.track.cues.push({line: 'auto', snapToLines: false, text: 'Later parsed cue'});
  env.video.fire('timeupdate'); assert.equal(translated.track.cues[1].line, -5);
  env.video.fire('loadedmetadata'); assert.equal(translated.track.mode, 'showing');
});
test('caption overlay shows active text safely and hands off to native mobile fullscreen', () => {
  const env = environment();
  const display = new Element(), text = new Element();
  const query = env.wrap.querySelector;
  env.wrap.querySelector = selector => selector === '[data-caption-display]' ? display : selector === '[data-caption-text]' ? text : query(selector);
  env.subtitleTracks[0].track.activeCues = [{text: '<script>literal caption</script>', getCueAsHTML: () => ({textContent: '<script>literal caption</script>'})}];
  env.load('player-controls.js');
  env.subtitleSelect.value = '0'; env.subtitleSelect.fire('change');
  assert.equal(env.subtitleTracks[0].track.mode, 'hidden');
  assert.equal(text.textContent, '<script>literal caption</script>');
  assert.equal(display.hidden, false);
  env.video.fire('webkitbeginfullscreen');
  assert.equal(env.subtitleTracks[0].track.mode, 'showing'); assert.equal(display.hidden, true);
  env.video.fire('webkitendfullscreen');
  assert.equal(env.subtitleTracks[0].track.mode, 'hidden'); assert.equal(display.hidden, false);
  env.subtitleSelect.value = 'off'; env.subtitleSelect.fire('change');
  assert.equal(display.hidden, true); assert.equal(text.textContent, '');
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
test('loading a resume position without playing does not write progress', async () => {
  const env = environment(), saves = [];
  env.context.postForm = async (url, data) => {
    if (url === '/progress') saves.push(data.position);
    return {url: '/demo.m3u8'};
  };
  env.video.canPlayType = () => 'maybe';
  env.context.csrfToken = () => 'token';
  env.context.navigator.sendBeacon = (_url, fields) => saves.push(Number(fields.get('position')));
  env.load('player.js');
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

test('next episode waits for opt-in, can be canceled, and never starts from a hidden tab', () => {
  const env = environment();
  const panel = new Element(), setting = new Element();
  const toggle = new Element('input'), cancel = new Element('button'), next = new Element('a');
  const countdown = new Element(), seconds = new Element(), announcement = new Element();
  env.doc.querySelector = selector => selector === '[data-next-episode]' ? panel : setting;
  setting.querySelector = () => toggle;
  const controls = new Map([
    ['[data-next-link]', next], ['[data-next-cancel]', cancel], ['[data-next-countdown]', countdown],
    ['[data-next-seconds]', seconds], ['[data-next-announcement]', announcement],
  ]);
  panel.querySelector = selector => controls.get(selector);
  next.href = '/watch/5/?play=1';
  next.focus = () => {};
  let activeTimer;
  const navigations = [];
  env.win.setInterval = callback => {activeTimer = callback; return 1;};
  env.win.clearInterval = () => {activeTimer = undefined;};
  env.win.location = {assign: href => navigations.push(href)};
  env.load('watch-next.js');
  env.video.ended = true;
  env.video.fire('ended');
  assert.equal(panel.hidden, false);
  assert.equal(activeTimer, undefined);
  toggle.checked = true;
  toggle.fire('change');
  env.video.fire('ended');
  assert.equal(seconds.textContent, '7');
  cancel.fire('click');
  assert.equal(activeTimer, undefined);
  assert.equal(cancel.hidden, true);
  env.video.fire('ended');
  env.doc.hidden = true;
  env.doc.fire('visibilitychange');
  assert.equal(activeTimer, undefined);
  env.doc.hidden = false;
  env.video.fire('ended');
  for (let second = 0; second < 6; second += 1) activeTimer();
  assert.deepEqual(navigations, []);
  activeTimer();
  assert.deepEqual(navigations, [next.href]);
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

test('room polling keeps member controls stable across chat updates', async () => {
  class RoomElement extends Element {
    constructor(tag) {super(tag); this.children = [];}
    get firstElementChild() {return this.children[0] ?? null;}
    get nextElementSibling() {
      return this.parentElement?.children[this.parentElement.children.indexOf(this) + 1] ?? null;
    }
    append(...nodes) {for (const node of nodes) this.insertBefore(node, null);}
    insertBefore(node, before) {
      node.remove();
      this.children.splice(before ? this.children.indexOf(before) : this.children.length, 0, node);
      node.parentElement = this;
    }
    remove() {
      if (!this.parentElement) return;
      this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1);
      this.parentElement = null;
    }
  }

  const env = environment();
  const room = new RoomElement(), messages = new RoomElement(), members = new RoomElement();
  const count = new RoomElement(), empty = new RoomElement();
  room.dataset = {host: 'true', user: '2', hostUser: '2', state: '/room-state'};
  room.querySelector = selector => selector === '[data-room-member-count]' ? count : empty;
  messages.append(empty);
  const controls = new Map([
    ['room', room], ['room-status', new RoomElement()], ['copy-invite', new RoomElement()],
    ['close-room', new RoomElement()], ['chat-form', new RoomElement()],
    ['chat-messages', messages], ['members', members],
  ]);
  const get = env.doc.getElementById;
  env.doc.getElementById = id => controls.get(id) || get(id);
  env.doc.createElement = tag => new RoomElement(tag);
  const roster = [{user_id: 1, user__username: 'Khách'}, {user_id: 2, user__username: 'Chủ phòng'}];
  let data = {members: roster, messages: []};
  let nextPoll;
  env.context.fetch = async () => ({ok: true, json: async () => data});
  env.context.setTimeout = callback => {nextPoll = callback;};
  env.load('room.js');
  await tick();

  const [host, guest] = members.children;
  assert.equal(host.dataset.memberId, '2');
  assert.equal(guest.dataset.memberId, '1');
  assert.equal(count.textContent, '2');
  assert.equal(empty.hidden, false);
  const actions = guest.children[3];
  const mute = new RoomElement('button');
  actions.append(mute);

  data = {members: roster, messages: [{id: 1, user: 'Chủ phòng', user_id: 2, content: '<em>Chào</em>'}]};
  await nextPoll();
  assert.equal(members.children[1], guest);
  assert.equal(guest.children[3].children[1], mute);
  assert.equal(empty.hidden, true);
  assert.equal(messages.children[0].children[1].textContent, '<em>Chào</em>');
  assert.equal(messages.children[0].dataset.own, 'true');

  data = {members: [roster[1]], messages: data.messages};
  await nextPoll();
  assert.deepEqual(members.children, [host]);
  assert.equal(count.textContent, '1');
  assert.equal(messages.children.length, 1);
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
