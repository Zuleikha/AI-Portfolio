---
document_id: card-authentication
title: Card Authentication and Authorisation
domain: cards
component: AuthorizationService
version: "4.2"
doc_type: reference
tags:
  - cards
  - authentication
  - authorisation
  - emv
---

# Card Authentication and Authorisation

AuthorizationService is the component that handles card authentication. It
establishes which card is presented, whether that card may be used, and whether
the transaction is authorised from the card's point of view. It delegates all
cryptographic work to CardSecurityModule.

## What "card authentication" covers

Card authentication is two lifecycle stages:

1. **Card identification** - resolve the presented card to a card record and
   check its status.
2. **PIN and cryptogram verification** - confirm the cardholder and confirm the
   card is genuine.

Both must pass before a transaction proceeds to limit evaluation. Neither of
them checks balances or limits, which is why a transaction can fail after
authentication has succeeded.

## Card identification

AuthorizationService looks up the card by its token. Clear PANs are never
stored, logged or passed between components; tokenisation happens at the
terminal or gateway boundary.

Checks applied, in order:

| Check | Failure code | Notes |
|---|---|---|
| Card record exists | `AUT-2001` | Unknown token, or a card that was never issued |
| Card is not blocked | `AUT-2004` | Blocked by the customer, by fraud rules, or by PIN retries |
| Card is not expired | `AUT-2007` | Expiry compared against transaction date |
| Card product permits the channel | `AUT-2012` | For example, a card not enabled for ATM use |
| Issuer country rules permit it | `AUT-2015` | Geographic restrictions on the card product |

## Cardholder verification

For chip transactions, AuthorizationService asks CardSecurityModule to:

- verify the encrypted PIN block, and
- validate the EMV application cryptogram to confirm the chip is genuine.

For magnetic-stripe fallback, only the PIN is verified. Fallback is permitted
only when `cards.allow_stripe_fallback` is enabled, and such transactions carry
a higher fraud score.

PIN failures increment a retry counter held against the card record. When the
counter reaches `cards.pin_retry_limit` the card is blocked and every subsequent
transaction fails with `AUT-2004` rather than a PIN error. This surprises
support staff: the customer entered the correct PIN, but the card was already
blocked by earlier attempts.

The retry counter resets on a successful PIN verification or on an explicit
unblock.

## The authorisation decision

After verification, AuthorizationService returns a decision:

| Decision | Meaning |
|---|---|
| `APPROVED` | Card checks passed; the transaction may continue to limits and funds |
| `DECLINED` | A card check failed; the transaction stops here |
| `REFERRED` | Manual review required; treated as a decline at an ATM |

An `APPROVED` decision is explicitly not a promise that the transaction will
complete. It says only that the card and cardholder are acceptable.

## Interfaces

AuthorizationService is called by TransactionSwitch for ATM and POS traffic, and
by PaymentEngine for digital payments. Both use the same authentication
endpoint, so a card blocked for ATM use is blocked for digital payments too.

## Data handling

- Card tokens, never clear PANs.
- PIN blocks are encrypted end to end and are never written to any log.
- Decision reasons are logged as codes, not as free text containing card data.
