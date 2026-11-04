import assert from 'node:assert/strict';
import test from 'node:test';
import { dashboardName, dashboardNumber } from './dashboard-format.ts';

test('uses a given name, without guessing from a login handle', () => {
  assert.equal(dashboardName('  abdul Wasea ', 'abdulw@example.com'), 'Abdul');
  assert.equal(dashboardName('abdulw', 'abdulw@example.com'), null);
  assert.equal(dashboardName(null), null);
  assert.equal(dashboardName('staff_123'), null);
});
test('formats exact and compact values, including zero and currency', () => {
  assert.equal(dashboardNumber(12400, undefined, true), '12.4K');
  assert.equal(dashboardNumber(12400), '12,400');
  assert.equal(dashboardNumber(0, 'USD', true), '$0.00');
  assert.equal(dashboardNumber(12400, 'USD', true), '$12.4K');
  assert.equal(dashboardNumber(12.35, 'EUR'), '€12.35');
});
