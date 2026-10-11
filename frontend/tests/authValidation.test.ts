import { test } from 'node:test'
import assert from 'node:assert/strict'
import { validateAuthForm } from '../src/lib/authValidation.ts'

test('rejects malformed emails in both modes', () => {
  for (const email of ['', 'nope', 'a@b', 'a b@c.co']) {
    assert.equal(validateAuthForm('login', email, 'x'), 'Enter a valid email address.', email)
    assert.equal(validateAuthForm('signup', email, 'abcdefg1'), 'Enter a valid email address.', email)
  }
})

test('sign-in only needs a password to be present', () => {
  assert.equal(validateAuthForm('login', 'a@b.co', ''), 'Enter your password.')
  assert.equal(validateAuthForm('login', 'a@b.co', 'x'), null)
})

test('sign-up enforces the same password rule as the backend', () => {
  for (const weak of ['short1', 'lettersonly', '12345678']) {
    assert.match(validateAuthForm('signup', 'a@b.co', weak) ?? '', /at least 8 characters/, weak)
  }
  assert.equal(validateAuthForm('signup', ' a@b.co ', 'abcdefg1'), null)
})
