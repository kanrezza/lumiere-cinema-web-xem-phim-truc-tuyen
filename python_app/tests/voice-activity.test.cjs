'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');

function environment({supported = true} = {}) {
  let now = 0;
  let nextInterval = 0;
  const intervals = new Map(), snapshots = [], contexts = [];
  class Track {
    enabled = true; muted = false; readyState = 'live'; amplitude = 0;
    listeners = new Map();
    addEventListener(name, callback) {this.listeners.set(name, callback);}
    removeEventListener(name, callback) {if (this.listeners.get(name) === callback) this.listeners.delete(name);}
    fire(name) {this.listeners.get(name)?.();}
  }
  class Stream {constructor(tracks) {this.tracks = tracks;} getAudioTracks() {return this.tracks;}}
  class Context {
    state = 'suspended'; nodes = [];
    constructor() {contexts.push(this);}
    createMediaStreamSource(stream) {
      const node = {disconnected: false, connect(target) {target.track = stream.getAudioTracks()[0];}, disconnect() {this.disconnected = true;}};
      this.nodes.push(node);
      return node;
    }
    createAnalyser() {
      const node = {fftSize: 512, disconnected: false, getFloatTimeDomainData(values) {values.fill(this.track.amplitude);}, disconnect() {this.disconnected = true;}};
      this.nodes.push(node);
      return node;
    }
    resume() {this.state = 'running'; return Promise.resolve();}
    suspend() {this.state = 'suspended'; return Promise.resolve();}
    close() {this.state = 'closed'; return Promise.resolve();}
  }
  const window = {
    AudioContext: supported ? Context : undefined,
    setInterval(callback, delay) {assert.equal(delay, 80); const id = ++nextInterval; intervals.set(id, callback); return id;},
    clearInterval(id) {intervals.delete(id);},
  };
  const module = loadFrontend('viewing/voice-activity.ts', {window, MediaStream: Stream, performance: {now: () => now}});
  const monitor = module.createVoiceActivityMonitor(snapshot => snapshots.push(JSON.parse(JSON.stringify(snapshot))));
  return {
    module, monitor, snapshots, contexts, intervals, Track,
    sample(time) {now = time; for (const callback of [...intervals.values()]) callback();},
    latest() {return snapshots.at(-1);},
  };
}

test('seats glow for sustained audio, retain between words, and stop after silence', () => {
  const env = environment(), track = new env.Track();
  env.monitor.resume(); env.monitor.attach('1', track, true);
  env.sample(0); env.sample(1000);
  assert.deepEqual(env.latest(), [{id: '1', speaking: false}]);
  track.amplitude = .03;
  env.sample(1100); env.sample(1260);
  assert.deepEqual(env.latest(), [{id: '1', speaking: true}]);
  track.amplitude = 0;
  env.sample(1300); env.sample(1500);
  assert.equal(env.latest()[0].speaking, true);
  env.sample(1650);
  assert.equal(env.latest()[0].speaking, false);
});

test('short noise impulses never show a speaker and the gate recovers from invalid data', () => {
  const {SpeechGate} = environment().module;
  const gate = new SpeechGate();
  gate.sample(.1, 0); gate.sample(0, 80); gate.sample(.1, 160);
  assert.equal(gate.speaking, false);
  gate.sample(.03, 320);
  assert.equal(gate.speaking, true);
  assert.equal(gate.sample(NaN, 400), true);
  assert.equal(gate.speaking, false);
});

test('host mute clears the glow immediately and disabled tracks cannot reactivate it', () => {
  const env = environment(), track = new env.Track();
  track.amplitude = .1;
  env.monitor.resume(); env.monitor.attach('2', track, true);
  env.sample(0); env.sample(160);
  assert.equal(env.latest()[0].speaking, true);
  env.monitor.setEnabled('2', false);
  assert.equal(env.latest()[0].speaking, false);
  env.sample(500); env.sample(1000);
  assert.equal(env.latest()[0].speaking, false);
  assert.equal(env.intervals.size, 0);
  assert.ok(env.contexts[0].nodes.every(node => node.disconnected));
});

test('remote track mute or end clears the source and preserves the full other-speaker snapshot', () => {
  const env = environment(), first = new env.Track(), second = new env.Track();
  first.amplitude = second.amplitude = .1;
  env.monitor.resume(); env.monitor.attach('1', first, true); env.monitor.attach('2', second, true);
  env.sample(0); env.sample(160);
  assert.deepEqual(env.latest(), [{id: '1', speaking: true}, {id: '2', speaking: true}]);
  first.muted = true; first.fire('mute');
  assert.deepEqual(env.latest(), [{id: '1', speaking: false}, {id: '2', speaking: true}]);
  first.readyState = 'ended'; first.fire('ended');
  assert.deepEqual(env.latest(), [{id: '2', speaking: true}]);
  assert.equal(first.listeners.size, 0);
});

test('leaving or disconnecting releases analysis nodes, timers and old track listeners', () => {
  const env = environment(), track = new env.Track();
  env.monitor.resume(); env.monitor.attach('1', track, true);
  env.monitor.suspend();
  assert.deepEqual(env.latest(), []);
  assert.equal(env.intervals.size, 0);
  assert.equal(track.listeners.size, 0);
  assert.equal(env.contexts[0].state, 'suspended');
  assert.ok(env.contexts[0].nodes.every(node => node.disconnected));
  env.monitor.resume(); env.monitor.attach('2', new env.Track(), true);
  assert.equal(env.contexts.length, 1);
  env.monitor.dispose(); env.monitor.resume();
  assert.equal(env.contexts[0].state, 'closed');
  assert.deepEqual(env.latest(), []);
  assert.equal(env.intervals.size, 0);
});

test('without Web Audio there are no timers, captures or simulated speaking states', () => {
  const env = environment({supported: false}), track = new env.Track();
  track.amplitude = .5;
  env.monitor.resume(); env.monitor.attach('1', track, true);
  env.sample(0); env.sample(1000);
  assert.deepEqual(env.latest(), [{id: '1', speaking: false}]);
  assert.equal(env.contexts.length, 0);
  assert.equal(env.intervals.size, 0);
  env.monitor.dispose();
  assert.equal(track.listeners.size, 0);
});
