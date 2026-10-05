# REQ-PAY-001: Submit a valid payment

Reference requirement: synthetic and suitable for public demonstration. It is not a transcription of RWA Cypress tests.

## Business intent
An authenticated account holder can send a valid payment to an eligible recipient.

## Risk level
HIGH

## Preconditions
- The sender is authenticated.

## Business conditions
- The recipient is eligible to receive a payment.
- The payment amount is positive.

## Acceptance criteria
- A valid payment is recorded once after submission.
- A successful payment is reflected in sender and recipient account state.

## Forbidden behaviors
- An invalid payment request does not create a transaction.

## State transitions
- Pending payment -> Valid payment submitted -> Recorded payment

## Explicit unknowns
- Insufficient-funds handling, fees, and payment limits are not specified.
