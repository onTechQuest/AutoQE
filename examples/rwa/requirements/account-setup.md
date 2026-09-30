# REQ-ACCT-001: Associate a bank account with its owner

Reference requirement: synthetic and suitable for public demonstration. It is not a transcription of RWA Cypress tests.

## Business intent
An authenticated user can set up a bank account associated with their own profile.

## Risk level
HIGH

## Preconditions
- The user is authenticated.

## Acceptance criteria
- A successfully created bank account is associated with the requesting authenticated user.

## Forbidden behaviors
- An unauthenticated user cannot create a bank account.

## Authorization constraints
- A user may manage only bank accounts associated with their own profile.

## Explicit unknowns
- Required account fields and account-number validation rules are not specified.