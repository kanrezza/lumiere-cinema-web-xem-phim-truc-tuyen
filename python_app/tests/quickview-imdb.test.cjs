'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const loadFrontend = require('./load-frontend.cjs');
const {imdbRating} = loadFrontend('shell/imdb.ts');

test('IMDb links use the canonical source and local rating format', () => {
  const rating = imdbRating('tt1254207', '6.5');
  assert.equal(rating.url, 'https://www.imdb.com/title/tt1254207/');
  assert.equal(rating.score, '6,5');
  assert.equal(imdbRating('', ''), undefined);
});

test('IMDb data rejects malformed IDs, injected URLs, missing scores and out-of-range values', () => {
  for (const [id, rating] of [
    ['javascript:alert(1)', '6.5'], ['tt1254207/evil', '6.5'], ['tt１２５４２０７', '6.5'],
    ['tt1254207', ''], ['tt1254207', '0.0'], ['tt1254207', '11.0'], ['tt1254207', 'NaN'],
    ['tt1254207', '6.5<script>'], ['tt1254207', '6,5'],
  ]) assert.equal(imdbRating(id, rating), undefined, `${id}: ${rating}`);
});

test('IMDb accepts both scale boundaries', () => {
  assert.equal(imdbRating('tt1254207', '1.0').score, '1,0');
  assert.equal(imdbRating('tt1254207', '10.0').score, '10,0');
});
