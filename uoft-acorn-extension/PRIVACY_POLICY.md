# UofT Agent Connector Privacy Policy

Last updated: 2026-04-07

## Summary

UofT Agent Connector is a Chrome extension that helps a user import their own ACORN academic history into UofT Agent.

The extension:

- does not collect usernames or passwords
- does not automate login
- only runs on `https://acorn.utoronto.ca/*`
- only imports data after the user has already logged in and manually clicks the import button
- sends parsed academic-history data to the UofT Agent backend only after the user initiates the import

## What data the extension processes

When the user clicks **Import Academic History**, the extension reads the visible academic-history page in ACORN and extracts academic records such as:

- course code
- course title
- credits / weight
- mark
- grade
- raw course text needed for parsing

The extension also sends:

- the user-provided import code
- a timestamp
- the ACORN page URL used for the import

## What data the extension does not collect

The extension does not collect:

- ACORN usernames
- ACORN passwords
- keyboard input outside the extension popup
- browsing history outside ACORN
- data from unrelated websites

## How data is used

Imported data is used only to let the user view their own ACORN academic history inside UofT Agent.

The extension sends the import payload to the UofT Agent backend endpoint configured in the extension source code.

## Data storage

The extension stores a small amount of local data in Chrome storage:

- the most recent import code entered by the user
- the most recent import payload for local extension flow support

The backend may store the imported academic-history payload so the UofT Agent web app can read it back using the same import code.

## User control

The extension only performs import when the user explicitly clicks the import button.

The user can stop using the extension at any time by:

- removing the extension from Chrome
- clearing extension storage in Chrome
- not using the import button

## Contact

For questions about this extension, contact the UofT Agent project maintainer through the project repository.
