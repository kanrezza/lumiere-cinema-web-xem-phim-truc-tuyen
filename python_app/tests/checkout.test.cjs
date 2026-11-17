'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const loadFrontend = require('./load-frontend.cjs');

function checkoutForm(disabled = false) {
  const attributes = new Map();
  const button = {
    disabled,
    setAttribute: (...args) => attributes.set(...args),
    removeAttribute: name => attributes.delete(name),
  };
  const status = {textContent: 'Tiếp tục tới cổng thanh toán'};
  const form = new EventTarget();
  form.querySelector = selector => selector === '[data-payment-submit]' ? button : status;
  const page = new EventTarget();
  const {bindCheckoutSubmission} = loadFrontend('public/checkout.ts');
  bindCheckoutSubmission(form, page);
  const submit = () => form.dispatchEvent(new Event('submit', {cancelable: true}));
  return {attributes, button, status, page, submit};
}

test('first submit proceeds, repeated submit is canceled, and back navigation restores the form', () => {
  const {button, attributes, status, page, submit} = checkoutForm();
  assert.equal(submit(), true);
  assert.equal(button.disabled, true);
  assert.equal(attributes.get('aria-busy'), 'true');
  assert.match(status.textContent, /Đang chuyển sang VNPay/);
  assert.equal(submit(), false);

  page.dispatchEvent(new Event('pageshow'));
  assert.equal(button.disabled, false);
  assert.equal(attributes.has('aria-busy'), false);
  assert.equal(status.textContent, 'Tiếp tục tới cổng thanh toán');
  assert.equal(submit(), true);
});

test('back navigation does not enable an unavailable payment method', () => {
  const {button, attributes, page} = checkoutForm(true);
  page.dispatchEvent(new Event('pageshow'));
  assert.equal(button.disabled, true);
  assert.equal(attributes.has('aria-busy'), false);
});
