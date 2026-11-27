'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');
const {allocateSeats, roomSeatCapacity, seatIsSpeaking, seatDisplayName} = loadFrontend('viewing/seat-state.ts');
const member = id => ({user_id: id, user__username: `viewer-${id}`});

test('roster polling retains assigned seats regardless of sort order', () => {
  const first = allocateSeats([], [member(3), member(1), member(2)], 1, 10);
  assert.deepEqual(Array.from(first.slice(0, 3)), [1, 3, 2]);
  const next = allocateSeats(first, [member(2), member(3), member(1), member(4)], 1, 10);
  assert.deepEqual(Array.from(next.slice(0, 4)), [1, 3, 2, 4]);
});
test('departing or kicked viewers free their seat without moving other occupants', () => {
  const previous = [1, 3, 2, 4, null, null, null, null, null, null];
  const next = allocateSeats(previous, [member(1), member(2), member(4), member(5)], 1, 10);
  assert.deepEqual(Array.from(next.slice(0, 4)), [1, 5, 2, 4]);
});
test('returning host takes the front seat without losing the displaced viewer', () => {
  const next = allocateSeats([3, 2, null, null], [member(3), member(2), member(1)], 1, 10);
  assert.deepEqual(Array.from(next.slice(0, 3)), [1, 2, 3]);
});
test('mic-on state alone never illuminates a seat, and muted audio cannot illuminate it', () => {
  assert.equal(seatIsSpeaking('speaking', false), false);
  assert.equal(seatIsSpeaking('speaking', true), true);
  for (const mode of ['muted', 'off', 'listening', undefined]) assert.equal(seatIsSpeaking(mode, true), false);
});
test('seats show the saved display name and fall back to username', () => {
  assert.equal(seatDisplayName({...member(1), display_name: 'Nguyễn An'}), 'Nguyễn An');
  assert.equal(seatDisplayName({...member(1), display_name: '  '}), 'viewer-1');
});

test('free rooms have exactly three seats including the host, even if the host is last in a stale roster', () => {
  const seats = Array.from(allocateSeats([], [member(2), member(3), member(4), member(1)], 1, 3));
  assert.deepEqual(seats, [1, 2, 3]);
  assert.equal(seats.length, 3);
});
test('VIP room capacity grows without moving occupied seats', () => {
  const seats = Array.from(allocateSeats([1, 3, 2], [member(4), member(2), member(1), member(3)], 1, 10));
  assert.equal(seats.length, 10);
  assert.deepEqual(seats.slice(0, 4), [1, 3, 2, 4]);
});
test('capacity downgrade retains the host and current occupants before polling roster order', () => {
  const seats = Array.from(allocateSeats([1, 3, 2, 4, null, null, null, null, null, null], [member(4), member(2), member(3), member(1)], 1, 3));
  assert.deepEqual(seats, [1, 3, 2]);
});
test('capacity downgrade brings occupants from removed seats into empty remaining seats', () => {
  const seats = Array.from(allocateSeats([null, null, null, 3, 1, 2, null, null, null, null], [member(2), member(3), member(1)], 1, 3));
  assert.deepEqual(seats, [1, 3, 2]);
});
test('seat capacity accepts server free and VIP values and preserves current capacity on partial snapshots', () => {
  assert.equal(roomSeatCapacity('3'), 3);
  assert.equal(roomSeatCapacity(10), 10);
  assert.equal(roomSeatCapacity(undefined), 3);
  assert.equal(roomSeatCapacity(undefined, 10), 10);
  for (const invalid of [0, 4, 100, -1, null, true, 'NaN', '']) assert.equal(roomSeatCapacity(invalid), 3);
});
