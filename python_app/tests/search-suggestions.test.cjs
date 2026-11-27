'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');
const state = loadFrontend('shell/search-state.ts', {URL, AbortController});
const {SearchSuggestionLoader: Loader, moveSearchSelection} = state;
const result = title => ({movies: [{id: 1, title, meta: '2026 · Phim lẻ', url: '/movies/test/', poster: '/media/poster.jpg', ready: true, vip: false}], actors: [], all_url: '/browse/?q=test'});
const reply = payload => ({ok: true, redirected: false, json: async () => payload});
const deferred = () => {let resolve, reject; const promise = new Promise((yes, no) => {resolve=yes; reject=no}); return {promise, resolve, reject};};

test('late search responses cannot replace a newer result even if fetch ignores abort', async () => {
  const requests = [];
  const loader = new Loader('/search/suggestions/', '/browse/', 'https://lumiere.example', (url, options) => {
    const pending=deferred(); requests.push({url, options, pending}); return pending.promise;
  });
  const old = loader.load('phim cu');
  const latest = loader.load('phim moi');
  assert.equal(requests[0].options.signal.aborted, true);
  assert.equal(requests[1].options.credentials, 'same-origin');
  requests[1].pending.resolve(reply(result('Phim mới')));
  assert.equal((await latest).movies[0].title, 'Phim mới');
  requests[0].pending.resolve(reply(result('Phim cũ')));
  assert.equal(await old, null);
});

test('cancelling search suppresses a delayed network error', async () => {
  const pending=deferred();
  const loader = new Loader('/search/suggestions/', '/browse/', 'https://lumiere.example', () => pending.promise);
  const request=loader.load('phim'); loader.cancel(); pending.reject(new Error('network'));
  assert.equal(await request, null);
});

test('short queries including a single decomposed Vietnamese letter make no request', async () => {
  let calls=0;
  const loader = new Loader('/search/suggestions/', '/browse/', 'https://lumiere.example', async () => {calls++; return reply(result('Movie'));});
  for (const query of ['', 'a', 'ắ', 'a\u0306\u0301']) assert.equal(await loader.load(query), null);
  assert.equal(calls, 0);
});

test('query is capped and encoded as a query parameter', async () => {
  let requested;
  const loader = new Loader('/search/suggestions/', '/browse/', 'https://lumiere.example', async url => {requested=url; return reply(result('Movie'));});
  await loader.load('a&b ?');
  assert.equal(new URL(requested, 'https://lumiere.example').searchParams.get('q'), 'a&b ?');
  await loader.load('x'.repeat(300));
  assert.equal(new URL(requested, 'https://lumiere.example').searchParams.get('q').length, 150);
});

test('API failure is surfaced while aborts are suppressed', async () => {
  const loader = new Loader('/search/suggestions/', '/browse/', 'https://lumiere.example', async () => ({ok:false, redirected:false}));
  await assert.rejects(loader.load('phim'), /unavailable/);
});

test('untrusted URLs and malformed rows are not turned into navigation targets', async () => {
  const payload = result('Valid');
  payload.movies.push({id:2,title:'External',meta:'2026',url:'//external.example/'});
  payload.movies.push({id:3,title:'Script',meta:'2026',url:'javascript:alert(1)'});
  payload.movies.push({id:4,title:'Backslash',meta:'2026',url:'/\\external.example/'});
  payload.movies.push(null);
  payload.actors=[{id:9,name:'Actor',url:'/actors/9/'},{id:10,name:'No',url:'https://external.example/'}];
  payload.all_url='javascript:alert(1)';
  const loader = new Loader('/search/suggestions/', '/browse/', 'https://lumiere.example', async () => reply(payload));
  const parsed=await loader.load('phim hay');
  assert.equal(parsed.movies.length,1);
  assert.equal(parsed.actors.length,1);
  assert.equal(parsed.all_url, '/browse/?q=phim+hay');
});

test('keyboard selection wraps and empty results leave no active descendant', () => {
  assert.equal(moveSearchSelection(-1, 0, 1), -1);
  assert.equal(moveSearchSelection(-1, 3, 1), 0);
  assert.equal(moveSearchSelection(-1, 3, -1), 2);
  assert.equal(moveSearchSelection(2, 3, 1), 0);
  assert.equal(moveSearchSelection(0, 3, -1), 2);
});
