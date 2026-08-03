import test from "node:test";
import assert from "node:assert/strict";
import { handleEnterToSubmit, handleEnterToRequestSubmit } from "./enterToSubmit.js";

function fakeKeyEvent({ key = "Enter", shiftKey = false, isComposing = false } = {}) {
  let prevented = false;
  return {
    key,
    shiftKey,
    nativeEvent: { isComposing },
    preventDefault() {
      prevented = true;
    },
    wasPrevented() {
      return prevented;
    },
    currentTarget: {
      form: {
        submitted: false,
        requestSubmit() {
          this.submitted = true;
        },
      },
    },
  };
}

test("Enter submits and prevents default", () => {
  const event = fakeKeyEvent();
  let called = 0;
  const handled = handleEnterToSubmit(event, () => {
    called += 1;
  });
  assert.equal(handled, true);
  assert.equal(called, 1);
  assert.equal(event.wasPrevented(), true);
});

test("Shift+Enter keeps newline (no submit)", () => {
  const event = fakeKeyEvent({ shiftKey: true });
  let called = 0;
  const handled = handleEnterToSubmit(event, () => {
    called += 1;
  });
  assert.equal(handled, false);
  assert.equal(called, 0);
  assert.equal(event.wasPrevented(), false);
});

test("IME composing does not submit", () => {
  const event = fakeKeyEvent({ isComposing: true });
  let called = 0;
  assert.equal(
    handleEnterToSubmit(event, () => {
      called += 1;
    }),
    false,
  );
  assert.equal(called, 0);
});

test("Enter requests form submit", () => {
  const event = fakeKeyEvent();
  handleEnterToRequestSubmit(event);
  assert.equal(event.currentTarget.form.submitted, true);
  assert.equal(event.wasPrevented(), true);
});
