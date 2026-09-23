---
document_id: payment-processing-overview
title: Payment Processing Overview
domain: payments
component: PaymentEngine
version: "4.2"
doc_type: reference
tags:
  - payments
  - clearing
  - settlement
  - reversal
---

# Payment Processing Overview

PaymentEngine handles the full life of a payment: authorisation, capture,
clearing, settlement and reversal. This document describes those phases and the
states a payment can occupy.

## Phases

```
Authorise  ->  Capture  ->  Clear  ->  Settle
    |             |
    +-> Expire    +-> Reverse
```

| Phase | What happens | Timing |
|---|---|---|
| Authorise | Funds reserved on the account, no ledger movement | Synchronous, sub-second |
| Capture | Funds moved from the account to the merchant position | Synchronous |
| Clear | Captured payments batched for the scheme or clearing system | Batched, per cycle |
| Settle | Net positions exchanged and confirmed | Once per settlement cycle |

Authorisation and capture are synchronous and customer-visible. Clearing and
settlement are batch processes and are not visible to the customer.

## Authorisation versus capture

A common misunderstanding is treating an authorisation as a completed payment.

- An authorisation reserves an amount and reduces available balance. The ledger
  balance is unchanged.
- A capture moves the money. Only after capture does the ledger balance change.
- An authorisation that is never captured expires after
  `payments.authorisation_validity_hours` and the reservation is released.

A customer seeing a reduced available balance for a payment they believe was
cancelled is usually looking at an uncaptured authorisation that has not yet
expired.

## Reversals

Reversals release an authorisation or refund a capture.

- Reversing an `AUTHORISED` payment releases the reservation immediately.
- Reversing a `CAPTURED` payment creates a refund, which follows the same
  clearing and settlement path as the original.
- Reversals are idempotent on the payment id.
- A reversal after clearing cannot be pulled back from that cycle; it settles in
  the next one.

## Clearing cycles

Captured payments are grouped into clearing batches. A batch is closed at the
end of its cycle and submitted. Payments captured after a cycle closes belong to
the next batch, which is why a payment captured late in the day can settle a day
later than one captured earlier.

Failed batch submissions are retried up to `payments.clearing_retry_count`. A
batch that still fails is held for operations rather than being dropped.

## Channel differences

| Channel | Entry point | Notes |
|---|---|---|
| Digital | DigitalGateway to PaymentEngine | Full authorise and capture flow |
| ATM | TransactionSwitch | Withdrawals authorise and capture in one step |
| POS | TransactionSwitch | Authorise at point of sale, capture in batch |

ATM withdrawals do not use the two-step model: the cash leaves the machine
immediately, so authorisation and capture happen together and any failure after
that point requires a reversal rather than an expiry.

## Where to look when a payment fails

The `decline_reason` on a `PAY-8003` response carries the underlying component
code. Start there rather than at PaymentEngine, since PaymentEngine is usually
reporting someone else's decision.
