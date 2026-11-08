'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    hidden: false, textContent: '', attrs: {}, listeners: {}, isConnected: true,
    classList: {toggle() {}, contains() {return false;}, add() {}, remove() {}},
    setAttribute(name, value) {this.attrs[name] = String(value);},
    removeAttribute(name) {delete this.attrs[name]; if (name === 'href') delete this.href;},
    addEventListener(name, fn) {this.listeners[name] = fn;}, focus() {},
  };
}

function setup() {
  const selectors = ['#quickview-title', '#quickview-image', '#quickview-meta',
    '#quickview-description', '#quickview-status', '#quickview-status-message',
    '#quickview-details', '#quickview-play', '#quickview-play-label', '#quickview-vip',
    '#quickview-cinema', '#quickview-trailer', '#quickview-imdb', '#quickview-imdb-score',
    '.quickview-close'];
  const nodes = Object.fromEntries(selectors.map(selector => [selector, element()]));
  const dialog = element();
  dialog.querySelector = selector => nodes[selector] || null;
  dialog.showModal = () => {dialog.open = true;};
  dialog.close = () => {dialog.open = false; dialog.listeners.close?.();};
  const trigger = element();
  trigger.dataset = {movieTitle: 'A film', movieDescription: 'A description', movieStatus: 'Đã có phim',
    movieReady: '1', movieStatusMessage: '', movieYear: '2008', movieKind: 'Phim lẻ',
    movieDuration: '10', movieImage: '/poster.jpg', movieDetail: '/movies/film/',
    movieVip: '0', movieCinema: '0', movieTrailer: '', moviePlay: '/watch/1/',
    moviePlayLabel: 'Xem ngay', movieImdbId: '', movieImdbRating: ''};
  const document = {getElementById: () => dialog,
    querySelectorAll: () => [trigger], body: element()};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/quickview.js'), 'utf8'), {document});
  return {nodes, trigger, open() {trigger.listeners.click();}};
}

test('IMDb opens a canonical source and then clears old source/rating for an unrated film', () => {
  const fixture = setup();
  fixture.trigger.dataset.movieImdbId = 'tt1254207';
  fixture.trigger.dataset.movieImdbRating = '6.5';
  fixture.open();
  const imdb = fixture.nodes['#quickview-imdb'];
  const score = fixture.nodes['#quickview-imdb-score'];
  assert.equal(imdb.hidden, false);
  assert.equal(imdb.href, 'https://www.imdb.com/title/tt1254207/');
  assert.equal(score.textContent, '6,5');
  fixture.trigger.dataset.movieImdbId = '';
  fixture.trigger.dataset.movieImdbRating = '';
  fixture.open();
  assert.equal(imdb.hidden, true);
  assert.equal(imdb.href, undefined);
  assert.equal(score.textContent, '');
});

test('IMDb data rejects malformed IDs, injected URLs, missing scores and out-of-range values', () => {
  const fixture = setup();
  for (const [id, rating] of [['javascript:alert(1)', '6.5'], ['tt1254207/evil', '6.5'],
    ['tt１２５４２０７', '6.5'], ['tt1254207', ''], ['tt1254207', '0.0'],
    ['tt1254207', '10.1'], ['tt1254207', 'NaN'], ['tt1254207', '6.5<script>'],
    ['tt1254207', '6,5']]) {
    fixture.trigger.dataset.movieImdbId = id;
    fixture.trigger.dataset.movieImdbRating = rating;
    fixture.open();
    assert.equal(fixture.nodes['#quickview-imdb'].hidden, true, `${id}: ${rating}`);
    assert.equal(fixture.nodes['#quickview-imdb'].href, undefined);
    assert.equal(fixture.nodes['#quickview-imdb-score'].textContent, '');
  }
});

test('IMDb accepts both scale boundaries without changing the movie playback target', () => {
  const fixture = setup();
  for (const rating of ['1.0', '10.0']) {
    fixture.trigger.dataset.movieImdbId = 'tt1254207';
    fixture.trigger.dataset.movieImdbRating = rating;
    fixture.open();
    assert.equal(fixture.nodes['#quickview-imdb'].hidden, false);
    assert.equal(fixture.nodes['#quickview-play'].href, '/watch/1/');
  }
});
