/**
 * Research Context overlay — thin compatibility wrapper around the unified account dialog.
 * Prefer AccountDialogOverlay in new call sites.
 */
import {
  AccountDialogOverlay,
  ACCOUNT_DIALOG_MODES,
} from "@/v2/AccountDialogOverlay";

export function ResearchContextOverlay({
  open,
  onClose,
  onChangeContext,
  onModeChange,
  ...rest
}) {
  return (
    <AccountDialogOverlay
      open={open}
      mode={ACCOUNT_DIALOG_MODES.research}
      onModeChange={(mode) => {
        onModeChange?.(mode);
        if (mode === ACCOUNT_DIALOG_MODES.preferences) onChangeContext?.();
      }}
      onClose={onClose}
      {...rest}
    />
  );
}
