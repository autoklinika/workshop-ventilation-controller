# iiyama Android kiosk — Stage 4

Stage 4 adds local, on-device management of service access for the dedicated iiyama HMI.

Scope:
- keep Stage 3 service exit by NFC card and 5 taps on active PULPIT + PIN;
- move service cards and PIN to persistent app-private storage;
- protect PIN verification with an Android Keystore-backed HMAC key;
- migrate the Stage 3 build-time card/PIN on first successful use so existing hardware access keeps working;
- add a native Service Mode screen after leaving Lock Task;
- allow adding an NFC card by presenting it to the panel and assigning a label;
- allow renaming and deleting service cards;
- allow changing the service PIN locally after entering Service Mode;
- provide direct buttons for Android Settings and returning to HMI;
- do not depend on CM5, WebGUI or network for service access.

Validation build remains testOnly until physical HMI validation is complete.

Do not merge to main without explicit project-owner approval.
