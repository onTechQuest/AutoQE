# REQ-AUTH-001: Authenticate an account holder

Reference requirement: synthetic and suitable for public demonstration. It is not a transcription of RWA Cypress tests.

## Business intent
Users should access their account only after successful authentication.

## Risk level
HIGH

## Acceptance criteria
- Valid account credentials establish an authenticated user session.
- Invalid credentials do not establish an authenticated user session.

## Explicit unknowns
- Session expiration duration and password policy are not specified.