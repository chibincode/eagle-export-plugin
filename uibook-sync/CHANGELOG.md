# UIBook Sync Changelog

## [0.2.3] - 2026-08-30

### Fixed

- Preserves the original cloud manual and automatic sync behavior when the live
  Edge Function is still the older POST-only version.
- Detects the known legacy status-query response and releases the pending-result
  lock instead of requiring a Lovable deployment before cloud sync can continue.
- In legacy compatibility mode, manual retry is available immediately and auto
  sync uses the original one-hour cooldown. A newer deployed function still gets
  precise timeout reconciliation automatically.

### Compatibility

Lovable deployment is optional for the existing cloud mode. It is only required
to enable Eagle Visual local analysis and precise post-timeout reconciliation.

## [0.2.2] - 2026-08-30

### Fixed

- Cloud synchronization now waits up to 180 seconds before declaring the result
  unknown, instead of treating a 60-second client timeout as a confirmed failure.
- Timed-out requests enter a persistent reconciliation queue and never enter the
  ordinary one-hour failure cooldown.
- The plugin checks the remote record by `sourceItemId` before allowing another
  upload, preventing duplicate AI work after a late Edge Function completion.
- Legacy recent timeout records are migrated into the reconciliation queue.

### Added

- Visible runtime plugin version in the settings window.
- Activity and summary states for `pending_confirmation`.
- Page-script and Node-testable recovery helpers in `js/sync-recovery.js`.

### Deployment

Deploy the matching UIBook `eagle-sync` status lookup before relying on automatic
reconciliation. The existing cloud and local analysis modes remain available.

## [0.2.1] - 2026-08-30

### Fixed

- Load local-analysis helpers explicitly as an Eagle page script so a renderer
  module-resolution failure cannot disable configuration, buttons, or timers.
- Show renderer boot failures inside the plugin window.
