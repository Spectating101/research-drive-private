/**
 * Enter submits / sends; Shift+Enter keeps a newline (IME-safe).
 * Use on textarea composers and single-line search textareas.
 */
export function handleEnterToSubmit(event, onSubmit) {
  if (event.key !== "Enter" || event.nativeEvent?.isComposing) return false;
  if (event.shiftKey) return false;
  event.preventDefault();
  onSubmit?.(event);
  return true;
}

/** Uncontrolled form field: Enter → form.requestSubmit(). */
export function handleEnterToRequestSubmit(event) {
  return handleEnterToSubmit(event, () => {
    event.currentTarget.form?.requestSubmit();
  });
}
