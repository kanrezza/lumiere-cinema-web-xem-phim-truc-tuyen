'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');
const {premierePosition, premierePlaybackPosition, premiereCountdown, countdownLabel} = loadFrontend('viewing/premiere-state.ts');

function snapshot(overrides = {}) {
  return {
    id: 'screening', status: 'live', position: 120, duration: 1800, playing: true,
    scheduled_at: '2026-11-25T13:00:00Z', server_time: '2026-11-25T12:58:30Z',
    ...overrides,
  };
}

test('joining a premiere advances from the server position rather than the viewer wall clock', () => {
  assert.equal(premierePosition(snapshot(), 2.25), 122.25);
  const thirtyMinutesLater = snapshot({server_time: '2026-11-25T13:28:30Z'});
  assert.equal(premierePosition(thirtyMinutesLater, 2.25), 122.25);
});

test('the premiere clock stops at the episode end and cannot go before the beginning', () => {
  assert.equal(premierePosition(snapshot({position: 1799}), 20), 1800);
  assert.equal(premierePosition(snapshot({position: -30}), -4), 0);
});

test('scheduled, cancelled, ended and paused snapshots do not keep advancing', () => {
  for (const status of ['scheduled', 'cancelled', 'ended']) {
    assert.equal(premierePosition(snapshot({status}), 90), 120);
  }
  assert.equal(premierePosition(snapshot({playing: false}), 90), 120);
});

test('invalid duration or position cannot send a seek outside the media bounds', () => {
  assert.equal(premierePosition(snapshot({duration: NaN}), 10), 0);
  assert.equal(premierePosition(snapshot({position: Infinity}), 10), 10);
  assert.equal(premierePosition(snapshot(), Infinity), 120);
});

test('countdown is based on server time, advances with elapsed time and never becomes negative', () => {
  assert.equal(premiereCountdown(snapshot()), 90);
  assert.equal(premiereCountdown(snapshot(), 12.4), 78);
  assert.equal(premiereCountdown(snapshot(), 120), 0);
  assert.equal(premiereCountdown(snapshot(), -30), 90);
  assert.equal(premiereCountdown(snapshot({scheduled_at: 'bad date'})), 0);
});

test('countdown labels remain readable for an event tomorrow and zero seconds', () => {
  assert.equal(countdownLabel(90061), '1 ngày · 01:01:01');
  assert.equal(countdownLabel(0), '00:00:00');
  assert.equal(countdownLabel(-9), '00:00:00');
  assert.equal(countdownLabel(NaN), '00:00:00');
});

test('live playback joins behind the aired clock so a seek cannot request future HLS segments', () => {
  assert.equal(premierePlaybackPosition(snapshot(), 3), 111);
  assert.equal(premierePlaybackPosition(snapshot({position: 5}), 0), 0);
  assert.equal(premierePlaybackPosition(snapshot({playback_delay_seconds: 18}), 3), 105);
  assert.equal(premierePlaybackPosition(snapshot({status: 'ended', position: 1800}), 10), 1788);
});
