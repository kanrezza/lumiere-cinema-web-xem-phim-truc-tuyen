'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');

function setup() {
  const connections = [], signals = [], sounds = [], analysis = [], timers = new Map();
  let timerId = 0, currentSession = 'self-session', recovering = false, microphone = null;
  class Connection {
    constructor() {
      this.events = new Map();
      this.connectionState = 'new';
      this.iceGatheringState = 'complete';
      this.replacedTracks = [];
      this.sender = {replaceTrack: async track => {this.replacedTracks.push(track)}};
      connections.push(this);
    }
    addEventListener(name, callback) {this.events.set(name, callback)}
    removeEventListener(name) {this.events.delete(name)}
    emit(name, detail = {}) {this.events.get(name)?.(detail)}
    async setRemoteDescription(description) {this.remoteDescription = description}
    async setLocalDescription(description) {this.localDescription = description}
    async createAnswer() {return {type: 'answer', sdp: 'm=audio 9 UDP/TLS/RTP/SAVPF 111'}}
    getTransceivers() {return [{sender: this.sender}]}
    close() {this.closed = true}
  }
  const {createVoicePeers} = loadFrontend('viewing/voice-peers.ts', {
    RTCPeerConnection: Connection,
    MediaStream: class {constructor(tracks) {this.tracks = tracks}},
    window: {
      setTimeout(callback) {const id = ++timerId; timers.set(id, callback); return id},
      clearTimeout(id) {timers.delete(id)},
    },
    document: {createElement() {
      const audio = {muted: true, setAttribute() {}, play: async () => {}, pause() {this.paused = true}, remove() {this.removed = true}};
      sounds.push(audio);
      return audio;
    }},
  });
  const member = {user_id: 1, voice_session: 'peer-session', mic_on: true, host_muted: false};
  const members = new Map([['1', member]]);
  const peers = createVoicePeers({
    selfId: '2', audioArea: {append() {}}, members,
    activity: {
      remove(id) {analysis.push(['remove', id])},
      attach(id, track, enabled) {analysis.push(['attach', id, track, enabled])},
      setEnabled(id, enabled) {analysis.push(['enabled', id, enabled])},
    },
    session: () => currentSession, recovering: () => recovering,
    microphone: () => microphone, iceServers: () => [],
    signal: async fields => {signals.push(fields)}, changed() {},
  });
  const offer = overrides => ({
    id: 1, from_user_id: 1, from_session: 'peer-session', type: 'offer',
    payload: {sdp: 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n', negotiation: 'negotiation-1'}, ...overrides,
  });
  return {peers, member, members, offer, connections, signals, sounds, analysis, timers,
    setSession(value) {currentSession = value},
    setRecovering(value) {recovering = value},
    setMicrophone(value) {microphone = value},
  };
}

test('voice negotiation ignores stale sessions and video before opening a connection', async () => {
  const s = setup();
  await s.peers.receiveSignal(s.offer({from_session: 'old-session'}));
  await s.peers.receiveSignal(s.offer({payload: {sdp: 'm=video 9 RTP/AVP 96', negotiation: 'video'}}));
  await s.peers.receiveSignal(s.offer({payload: {sdp: 'm=audio 9 RTP/AVP 111\nm=video 9 RTP/AVP 96', negotiation: 'mixed'}}));
  assert.equal(s.connections.length, 0);
  await s.peers.receiveSignal(s.offer());
  assert.equal(s.connections.length, 1);
  assert.equal(s.signals[0].target_session, 'peer-session');
  assert.equal(s.signals[0].session, 'self-session');
  assert.equal(s.signals[0].type, 'answer');
  assert.equal(JSON.parse(s.signals[0].payload).negotiation, 'negotiation-1');
  assert.deepEqual(s.connections[0].replacedTracks, [null]);
});

test('host mute immediately silences a connected peer and closes activity with reset', async () => {
  const s = setup();
  await s.peers.receiveSignal(s.offer());
  const track = {kind: 'audio'};
  s.connections[0].emit('track', {track});
  assert.equal(s.sounds[0].muted, false);
  assert.deepEqual(s.analysis.at(-1), ['enabled', '1', true]);
  s.member.host_muted = true;
  s.peers.reconcile();
  assert.equal(s.sounds[0].muted, true);
  assert.deepEqual(s.analysis.at(-1), ['enabled', '1', false]);
  s.peers.reset();
  assert.equal(s.connections[0].closed, true);
  assert.equal(s.sounds[0].srcObject, null);
  assert.equal(s.sounds[0].removed, true);
  assert.equal(s.timers.size, 0);
});

test('a changed member session cannot keep old audio or old negotiation alive', async () => {
  const s = setup();
  await s.peers.receiveSignal(s.offer());
  s.member.voice_session = 'replacement-session';
  s.peers.reconcile();
  assert.equal(s.connections[0].closed, true);
  await s.peers.receiveSignal(s.offer());
  assert.equal(s.connections.length, 1);
  await s.peers.receiveSignal(s.offer({from_session: 'replacement-session'}));
  assert.equal(s.connections.length, 2);
  assert.equal(s.signals.at(-1).target_session, 'replacement-session');
});

test('connection retries stop when a participant leaves and recovery suppresses offers', async () => {
  const s = setup();
  await s.peers.receiveSignal(s.offer());
  s.connections[0].connectionState = 'failed';
  s.connections[0].emit('connectionstatechange');
  assert.equal(s.peers.retrying(), true);
  assert.equal(s.connections[0].closed, true);
  s.member.voice_session = null;
  s.peers.reconcile();
  assert.equal(s.peers.retrying(), false);
  s.setRecovering(true);
  s.members.set('3', {user_id: 3, voice_session: 'new-session', mic_on: false, host_muted: false});
  s.peers.reconcile();
  assert.equal(s.connections.length, 1);
});
