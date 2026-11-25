'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');

class Element extends EventTarget {
  constructor() {
    super();
    this.nodes = new Map();
    this.attributes = new Map();
    this.style = {overflow: ''};
    this.classes = new Set();
    this.classList = {add: name => this.classes.add(name), remove: name => this.classes.delete(name), contains: name => this.classes.has(name)};
    this.textContent = '';
    this.focused = 0;
  }
  querySelector(selector) {return this.nodes.get(selector) || null;}
  setAttribute(name, value) {this.attributes.set(name, value);}
  getAttribute(name) {return this.attributes.get(name) ?? null;}
  focus() {this.focused++;}
  fire(name, fields = {}) {const event = new Event(name); Object.assign(event, fields); this.dispatchEvent(event);}
}

function environment() {
  const room = new Element(), button = new Element(), label = new Element(), status = new Element();
  const approval = new Element(), dialog = new Element(), close = new Element();
  room.nodes = new Map([
    ['[data-cinema-fullscreen]', button], ['#room-status', status],
    ['[data-room-approval-toggle]', approval], ['[data-room-approval-dialog]', dialog],
  ]);
  button.nodes.set('[data-cinema-fullscreen-label]', label);
  dialog.nodes.set('[data-room-approval-close]', close);
  dialog.open = false;
  dialog.showModal = () => {dialog.open = true;};
  dialog.close = () => {dialog.open = false; dialog.fire('close');};
  dialog.getBoundingClientRect = () => ({left: 10, top: 10, right: 50, bottom: 50});
  const doc = new Element(), win = new Element();
  win.setTimeout = setTimeout;
  win.clearTimeout = clearTimeout;
  doc.body = new Element();
  doc.activeElement = approval;
  doc.fullscreenElement = null;
  const {initCinemaControls} = loadFrontend('viewing/cinema-controls.ts', {
    document: doc, window: win, HTMLElement: Element, AbortController,
  });
  const dispose = initCinemaControls(room);
  return {room, button, label, status, approval, dialog, close, doc, win, dispose};
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('cinema fullscreen uses the actual fullscreen API and restores its label on exit', async () => {
  const env = environment();
  env.room.requestFullscreen = async () => {env.doc.fullscreenElement = env.room; env.doc.fire('fullscreenchange');};
  env.doc.exitFullscreen = async () => {env.doc.fullscreenElement = null; env.doc.fire('fullscreenchange');};
  env.button.fire('click'); await tick();
  assert.equal(env.doc.fullscreenElement, env.room);
  assert.equal(env.button.getAttribute('aria-pressed'), 'true');
  assert.equal(env.label.textContent, 'Thu nhỏ rạp');
  env.button.fire('click'); await tick();
  assert.equal(env.doc.fullscreenElement, null);
  assert.equal(env.label.textContent, 'Phóng to rạp');
  env.dispose();
});

test('denied fullscreen reports failure without pretending the room is fullscreen', async () => {
  const env = environment();
  env.room.requestFullscreen = async () => {throw new Error('Fullscreen denied');};
  env.button.fire('click'); await new Promise(resolve => setTimeout(resolve, 200));
  assert.equal(env.button.getAttribute('aria-pressed'), 'false');
  assert.equal(env.room.classList.contains('is-immersive'), false);
  assert.match(env.status.textContent, /chưa cho phép/);
  env.dispose();
});

test('a rejected exit promise is successful when fullscreen has actually exited', async () => {
  const env = environment();
  env.doc.fullscreenElement = env.room;
  env.doc.fire('fullscreenchange');
  env.doc.exitFullscreen = async () => {
    env.doc.fullscreenElement = null;
    env.doc.fire('fullscreenchange');
    throw new Error('Embedded browser rejected after exit');
  };
  env.button.fire('click'); await tick();
  assert.equal(env.doc.fullscreenElement, null);
  assert.equal(env.button.getAttribute('aria-pressed'), 'false');
  assert.equal(env.status.textContent, '');
  env.dispose();
});

test('a rejected fullscreen promise waits for the resulting transition before reporting an error', async () => {
  const env = environment();
  env.doc.fullscreenElement = env.room;
  env.doc.fire('fullscreenchange');
  env.doc.exitFullscreen = async () => {
    setTimeout(() => {env.doc.fullscreenElement = null; env.doc.fire('fullscreenchange');}, 10);
    throw new Error('Transition in progress');
  };
  env.button.fire('click'); await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(env.button.getAttribute('aria-pressed'), 'false');
  assert.equal(env.status.textContent, '');
  env.dispose();
});

test('successful fullscreen clears only this control\'s prior error, preserving unrelated room messages', async () => {
  const env = environment();
  env.room.requestFullscreen = async () => {throw new Error('Denied');};
  env.button.fire('click'); await new Promise(resolve => setTimeout(resolve, 200));
  assert.match(env.status.textContent, /chưa cho phép/);
  env.room.requestFullscreen = async () => {env.doc.fullscreenElement = env.room; env.doc.fire('fullscreenchange');};
  env.button.fire('click'); await tick();
  assert.equal(env.status.textContent, '');
  env.status.textContent = 'Tin nhắn phòng cần giữ lại.';
  env.doc.exitFullscreen = async () => {env.doc.fullscreenElement = null; env.doc.fire('fullscreenchange');};
  env.button.fire('click'); await tick();
  assert.equal(env.status.textContent, 'Tin nhắn phòng cần giữ lại.');
  env.dispose();
});

test('unsupported fullscreen uses an explicit viewport fallback and Escape restores scrolling', async () => {
  const env = environment();
  env.doc.body.style.overflow = 'auto';
  env.button.fire('click'); await tick();
  assert.equal(env.room.classList.contains('is-immersive'), true);
  assert.equal(env.doc.body.style.overflow, 'hidden');
  assert.match(env.status.textContent, /chưa hỗ trợ toàn màn hình/);
  env.doc.fire('keydown', {key: 'Escape'});
  assert.equal(env.room.classList.contains('is-immersive'), false);
  assert.equal(env.doc.body.style.overflow, 'auto');
  assert.equal(env.button.focused, 1);
  env.dispose();
});

test('approval dialog opens from its host control and returns focus on close', () => {
  const env = environment();
  env.approval.fire('click');
  assert.equal(env.dialog.open, true);
  assert.equal(env.approval.getAttribute('aria-expanded'), 'true');
  assert.equal(env.close.focused, 1);
  env.close.fire('click');
  assert.equal(env.dialog.open, false);
  assert.equal(env.approval.getAttribute('aria-expanded'), 'false');
  assert.equal(env.approval.focused, 1);
  env.dispose();
});

test('disposing controls closes the approval dialog and removes page listeners', async () => {
  const env = environment();
  env.approval.fire('click');
  env.button.fire('click'); await tick();
  env.dispose();
  assert.equal(env.dialog.open, false);
  assert.equal(env.room.classList.contains('is-immersive'), false);
  env.approval.fire('click');
  env.button.fire('click'); await tick();
  assert.equal(env.dialog.open, false);
  assert.equal(env.room.classList.contains('is-immersive'), false);
});
