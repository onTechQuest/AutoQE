# REQ-AUTHZ-001: Restrict account data to its owner

Reference requirement: synthetic and suitable for public demonstration. It is not a transcription of RWA Cypress tests.

## Business intent
Users may access or change only account data they are authorized to own.

## Risk level
CRITICAL

## Preconditions
- A target account or profile belongs to a user.
- A request is made by an authenticated user.

## Acceptance criteria
- The owner can access their own private account data.

## Forbidden behaviors
- A non-owner cannot access another user's private account data.
- A non-owner cannot change another user's private account data.

## Authorization constraints
- Private account access and changes are limited to the account owner.

## Explicit unknowns
- Administrative access and delegated ownership rules are not specified.