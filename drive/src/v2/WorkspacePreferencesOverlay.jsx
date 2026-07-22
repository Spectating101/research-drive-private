/**
 * Workspace Preferences overlay — thin compatibility wrapper around the unified account dialog.
 * Prefer AccountDialogOverlay in new call sites.
 */
import {
  AccountDialogOverlay,
  ACCOUNT_DIALOG_MODES,
} from "@/v2/AccountDialogOverlay";

export function WorkspacePreferencesOverlay({
  open,
  onClose,
  mode: _mode,
  initialAdvancedOpen = false,
  ...rest
}) {
  return (
    <AccountDialogOverlay
      open={open}
      mode={ACCOUNT_DIALOG_MODES.preferences}
      onClose={onClose}
      preferencesActiveGroup={initialAdvancedOpen ? "advanced" : "workspace"}
      {...rest}
    />
  );
}
