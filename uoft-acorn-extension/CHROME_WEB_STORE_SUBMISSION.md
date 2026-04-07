# Chrome Web Store Submission Notes

These files are prepared to support Chrome Web Store submission for the UofT Agent Connector extension.

## Included

- `manifest.json`
- `popup.html`
- `popup.js`
- `background.js`
- `content.js`
- `styles.css`
- `utils/`
- `icons/`
- `PRIVACY_POLICY.md`
- `privacy-policy.html`

## Suggested Store Summary

Import your ACORN academic history into UofT Agent after logging in normally.

## Suggested Store Description

UofT Agent Connector helps University of Toronto students import their own ACORN academic history into UofT Agent.

How it works:

1. Open UofT Agent and copy your import code
2. Log into ACORN normally
3. Open the extension popup
4. Paste the import code
5. Click "Import Academic History"

The extension does not collect passwords or automate login. It only runs on ACORN pages and only imports visible academic-history data after the user explicitly clicks the import button.

## Permissions Justification

- `activeTab`: used to communicate with the currently active ACORN tab
- `scripting`: required for extension scripting flow
- `storage`: used to store the last import code and recent import payload locally
- host permissions for `acorn.utoronto.ca`: needed to read the logged-in academic-history page
- host permissions for the UofT Agent backend: needed to send the import payload

## Before Submission

- Replace placeholder icons in `icons/` with final branded assets
- Host the privacy policy at a public URL
- Add the privacy policy URL in the Chrome Web Store listing
- Verify the production backend URL in `background.js`
- Reload the unpacked extension and test one full import flow
