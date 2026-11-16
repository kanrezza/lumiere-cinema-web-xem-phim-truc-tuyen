'use strict';
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const {buildSync} = createRequire(path.join(__dirname, '../frontend/package.json'))('esbuild');

const bundles = new Map();

module.exports = function loadFrontend(entry, globals = {}) {
  if (!bundles.has(entry)) {
    const script = buildSync({
      entryPoints: [path.join(__dirname, '../frontend/src', entry)],
      bundle: true, write: false, platform: 'browser', format: 'iife', globalName: 'LumiereTest',
    }).outputFiles[0].text;
    bundles.set(entry, script);
  }
  return vm.runInNewContext(bundles.get(entry) + '\nLumiereTest;', globals, {filename: entry});
};
