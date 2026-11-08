'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag = 'div') {this.tag = tag; this.children = []; this.listeners = new Map(); this.dataset = {}; this.attributes = {}; this.value = ''; this.hidden = false; this.disabled = false; this.textContent = ''; if (tag === 'track') this.track = {mode: 'disabled'};}
  addEventListener(type, callback) {const list = this.listeners.get(type) || []; list.push(callback); this.listeners.set(type, list);}
  dispatchEvent(event) {event.target ||= this; for (const callback of this.listeners.get(event.type) || []) callback(event); return !event.defaultPrevented;}
  fire(type, data = {}) {const event = {type, defaultPrevented: false, preventDefault() {this.defaultPrevented = true;}, ...data}; this.dispatchEvent(event); return event;}
  setAttribute(name, value) {this.attributes[name] = String(value);}
  getAttribute(name) {return this.attributes[name] || null;}
  append(...elements) {for (const element of elements) {element.parent = this; this.children.push(element);}}
  replaceChildren(...elements) {for (const element of this.children) element.parent = null; this.children = []; this.append(...elements);}
  remove() {if (this.parent) {this.parent.children = this.parent.children.filter(element => element !== this); this.parent = null;}}
  get options() {return this.children;}
  contains(element) {return this === element || this.children.some(child => child.contains(element));}
  focus() {this.focused = true;}
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function fixture({empty = false, responses = []} = {}) {
  const video = new Element('video'), wrap = new Element(), panel = new Element(), toggle = new Element('button');
  const close = new Element('button'), selection = new Element('select'), source = new Element('select'), target = new Element('select');
  const translateForm = new Element('form'), translateButton = new Element('button'), translateStatus = new Element();
  const generateForm = new Element('form'), speechLanguage = new Element('select'), generateButton = new Element('button'), generateStatus = new Element();
  const emptyNode = new Element();
  panel.hidden = true; panel.dataset.captionScope = '/watch/1/';
  selection.value = 'off'; source.value = empty ? '' : '1'; target.value = 'vi'; speechLanguage.value = 'auto';
  generateForm.attributes.action = '/watch/1/captions/generate/';
  const off = new Element('option'); off.value = 'off'; selection.append(off);
  if (!empty) {
    const track = new Element('track'); track.dataset = {subtitle: '', subtitleId: '1'}; track.label = 'English'; track.srclang = 'en'; video.append(track);
    const option = new Element('option'); option.value = '0'; selection.append(option);
    const original = new Element('option'); original.value = '1'; original.dataset = {language: 'en', translateUrl: '/watch/1/subtitles/1/translate/'}; source.append(original);
  }
  const selectors = new Map([
    ['[data-caption-close]', close], ['.player-subtitles', selection], ['[data-caption-source]', source], ['[data-caption-target]', target],
    ['[data-caption-form]', translateForm], ['[data-caption-submit]', translateButton], ['[data-caption-status]', translateStatus],
    ['[data-caption-generate]', generateForm], ['[data-caption-speech-language]', speechLanguage], ['[data-caption-generate-submit]', generateButton],
    ['[data-caption-generate-status]', generateStatus], ['[data-caption-empty]', empty ? emptyNode : null],
  ]);
  panel.querySelector = selector => selectors.get(selector) || null;
  panel.append(...[...selectors.values()].filter(Boolean));
  wrap.querySelector = selector => selector === '[data-caption-panel]' ? panel : selector === '[data-caption-toggle]' ? toggle : null;
  wrap.append(video, panel, toggle); video.closest = () => wrap;
  video.querySelectorAll = selector => video.children.filter(element => element.tag === 'track' && (selector.includes('data-translated') ? element.dataset.translated === 'true' : Object.hasOwn(element.dataset, 'subtitle')));
  const doc = new Element(), win = new Element();
  doc.getElementById = id => id === 'player' ? video : null; doc.createElement = tag => new Element(tag);
  win.location = {origin: 'http://127.0.0.1:8000', href: 'http://127.0.0.1:8000/watch/1/'}; win.csrfToken = () => 'test-csrf';
  let timerId = 0; const timers = new Map(), requests = [];
  const context = {document: doc, window: win, URL, URLSearchParams, AbortController,
    CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
    setTimeout(callback, delay) {timers.set(++timerId, {callback, delay}); return timerId;}, clearTimeout(id) {timers.delete(id);},
    async fetch(url, options) {requests.push({url, options}); const next = responses.shift(); if (!next) throw new Error('Missing test response'); if (next.then) return next; return {ok: next.ok !== false, async json() {return next.payload || next;}};},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/caption-panel.js'), 'utf8'), context);
  return {video, panel, toggle, close, selection, source, target, translateForm, translateButton, translateStatus, generateForm, speechLanguage, generateButton, generateStatus, emptyNode, doc, win, timers, requests,
    async poll() {const item = [...timers.entries()].find(([, value]) => value.delay === 1500); assert.ok(item, 'poll was scheduled'); timers.delete(item[0]); await item[1].callback(); await tick();}};
}
const ready = {id: 'job', status: 'ready', target: 'vi', label: 'Tiếng Việt (dịch tự động)', status_url: '/watch/1/translations/job/', track_url: '/watch/1/translations/job.vtt', error: ''};

test('caption button opens the empty panel and supports Escape, outside click and focus return', () => {
  const env = fixture({empty: true});
  assert.equal(env.translateButton.disabled, true);
  env.toggle.fire('click'); assert.equal(env.panel.hidden, false); assert.equal(env.toggle.attributes['aria-expanded'], 'true'); assert.equal(env.close.focused, true);
  const event = env.doc.fire('keydown', {key: 'Escape'}); assert.equal(event.defaultPrevented, true); assert.equal(env.panel.hidden, true); assert.equal(env.toggle.focused, true);
  env.toggle.fire('click'); env.doc.fire('click', {target: new Element()}); assert.equal(env.panel.hidden, true);
});

test('ready translation adds a native track, activates its option and sends CSRF with the target', async () => {
  const env = fixture({responses: [ready]}); let changed;
  env.video.addEventListener('lumiere:captions-changed', event => {changed = event.detail.selected;});
  env.translateForm.fire('submit'); await tick();
  assert.equal(env.requests.length, 1); assert.equal(env.requests[0].options.headers['X-CSRFToken'], 'test-csrf');
  assert.equal(env.requests[0].options.body.get('target'), 'vi'); assert.equal(env.requests[0].options.credentials, 'same-origin');
  assert.equal(env.video.children.length, 2); assert.equal(env.video.children[1].src, 'http://127.0.0.1:8000/watch/1/translations/job.vtt');
  assert.equal(env.selection.value, '1'); assert.equal(changed, '1'); assert.match(env.translateStatus.textContent, /Đã bật/);
});

test('pending translation waits for a ready job before adding any track', async () => {
  const env = fixture({responses: [{...ready, status: 'pending', track_url: null}, ready]});
  env.translateForm.fire('submit'); await tick();
  assert.equal(env.video.children.length, 1); assert.equal(env.translateButton.disabled, true);
  await env.poll(); assert.equal(env.video.children.length, 2); assert.equal(env.translateButton.disabled, false);
});

test('unconfigured or failed translation reports its actual error without pretending success', async () => {
  for (const response of [{ok: false, payload: {error: 'Dịch tự động chưa được cấu hình.'}}, {...ready, status: 'failed', error: 'Không tìm thấy cặp ngôn ngữ.'}]) {
    const env = fixture({responses: [response]}); env.translateForm.fire('submit'); await tick();
    assert.equal(env.video.children.length, 1); assert.equal(env.translateStatus.dataset.error, 'true');
    assert.doesNotMatch(env.translateStatus.textContent, /Đã bật/); assert.equal(env.translateButton.disabled, false);
  }
});

test('untrusted cross-origin track and polling URLs are rejected', async () => {
  for (const response of [{...ready, track_url: 'https://example.test/stolen.vtt'}, {...ready, status: 'pending', status_url: 'https://example.test/job/'}]) {
    const env = fixture({responses: [response]}); env.translateForm.fire('submit'); await tick();
    assert.equal(env.video.children.length, 1); assert.equal(env.requests.length, 1); assert.equal(env.translateStatus.dataset.error, 'true');
  }
});

test('changing target cancels polling and removes a previously selected generated translation', async () => {
  const env = fixture({responses: [ready, {...ready, status: 'pending', track_url: null}]});
  env.translateForm.fire('submit'); await tick(); assert.equal(env.selection.value, '1');
  env.target.value = 'en'; env.target.fire('change'); assert.equal(env.video.children.length, 1); assert.equal(env.selection.value, 'off');
  env.target.value = 'vi'; env.translateForm.fire('submit'); await tick(); assert.ok([...env.timers.values()].some(item => item.delay === 1500));
  env.target.fire('change'); assert.equal([...env.timers.values()].some(item => item.delay === 1500), false);
});

test('speech generation on an empty film adds an original source and enables translation', async () => {
  const job = {status: 'ready', subtitle: {id: 9, language: 'en', label: 'English (tự động)', url: '/watch/1/subtitles/9.vtt', translate_url: '/watch/1/subtitles/9/translate/'}};
  const env = fixture({empty: true, responses: [job]});
  env.generateForm.fire('submit'); await tick();
  assert.equal(env.requests[0].options.body.get('language'), 'auto');
  assert.equal(env.video.children.length, 1); assert.equal(env.video.children[0].dataset.subtitleId, '9');
  assert.equal(env.source.value, '9'); assert.equal(env.source.disabled, false); assert.equal(env.translateButton.disabled, false); assert.equal(env.emptyNode.hidden, true);
});

test('a new original source removes the older translation and keeps picker indices consistent', async () => {
  const generated = {status: 'ready', subtitle: {id: 9, language: 'en', label: 'English (tự động)', url: '/watch/1/subtitles/9.vtt', translate_url: '/watch/1/subtitles/9/translate/'}};
  const env = fixture({responses: [ready, generated]}); env.translateForm.fire('submit'); await tick();
  env.generateForm.fire('submit'); await tick(); assert.equal(env.selection.value, '1');
  env.target.value = 'en'; env.target.fire('change');
  assert.equal(env.video.children.length, 2); assert.equal(env.selection.value, '1'); assert.equal(env.selection.options.at(-1).value, '1');
});

test('pagehide cancels pending polls so a closed page cannot activate captions later', async () => {
  const env = fixture({responses: [{...ready, status: 'pending', track_url: null}]}); env.translateForm.fire('submit'); await tick();
  env.win.fire('pagehide'); assert.equal([...env.timers.values()].some(item => item.delay === 1500), false); assert.equal(env.video.children.length, 1);
});

test('a newly generated source supersedes any late translation from the old source', async () => {
  let resolveOld;
  const pendingOld = new Promise(resolve => {resolveOld = resolve;});
  const generated = {status: 'ready', subtitle: {id: 9, language: 'en', label: 'English (tự động)', url: '/watch/1/subtitles/9.vtt', translate_url: '/watch/1/subtitles/9/translate/'}};
  const env = fixture({responses: [pendingOld, generated]});
  env.translateForm.fire('submit'); await tick();
  env.generateForm.fire('submit'); await tick();
  resolveOld({ok: true, async json() {return ready;}}); await tick();
  assert.equal(env.source.value, '9'); assert.equal(env.video.children.length, 2);
  assert.equal(env.video.children.some(track => track.dataset.translated === 'true'), false);
});
