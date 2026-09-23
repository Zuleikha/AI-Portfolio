---
document_id: platform-component-overview
title: Meridian Platform Component Overview
domain: platform
component: Platform
version: "4.2"
doc_type: reference
tags:
  - architecture
  - components
  - overview
---

# Meridian Platform Component Overview

Meridian is a self-service and digital banking platform. This document lists the
runtime components, what each one owns, and how a request moves between them. It
is the starting point for anyone tracing a transaction across services.

> All content in this knowledge base is synthetic and written for this project.
> It does not describe any real vendor product.

## Runtime components

| Component | Code | Owns |
|---|---|---|
| TransactionSwitch | `SWX` | Routing and orchestration of ATM and POS transactions |
| AuthorizationService | `AUT` | Card identification, status checks, authorisation decision |
| CardSecurityModule | `CSM` | PIN block translation, EMV cryptogram validation, HSM access |
| LimitService | `LIM` | Transaction, daily and velocity limit evaluation |
| CoreBankingAdapter | `COR` | Balance enquiry, debit and credit posting to the core ledger |
| PaymentEngine | `PAY` | Payment authorisation, capture, reversal and settlement |
| DigitalGateway | `DGW` | Mobile and web banking channel entry point |
| DeviceManager | `DEV` | ATM device state, cassette levels, hardware health |
| ConfigurationStore | `CFG` | Versioned configuration distribution to every component |

Each component prefixes its error codes with its own code, so `LIM-4001` is
always a LimitService error regardless of which channel surfaced it. The full
list is in the error code reference.

## Request path for an ATM withdrawal

```
ATM terminal
   -> TransactionSwitch        routing, orchestration, timeouts, reversals
        -> AuthorizationService   card status and authorisation decision
             -> CardSecurityModule  PIN and cryptogram verification
        -> LimitService            limit evaluation
        -> CoreBankingAdapter      funds check and ledger posting
   -> DeviceManager            dispense instruction and confirmation
```

TransactionSwitch is the only component that talks to the terminal. Everything
else is reached through it, which is why almost every end-to-end timeout is
reported as a `SWX-` code even when the underlying fault is elsewhere.

## Request path for a digital payment

```
Mobile or web client
   -> DigitalGateway           session, channel validation, request shaping
        -> PaymentEngine          authorisation and capture
             -> AuthorizationService   instrument checks
             -> LimitService           limit evaluation
             -> CoreBankingAdapter     ledger posting
```

## Separation of responsibilities

- **Authentication is not authorisation.** AuthorizationService establishes
  *who the card is and whether it may be used*. It does not decide whether the
  account has money or headroom; LimitService and CoreBankingAdapter do.
- **CardSecurityModule never sees clear PINs.** It receives encrypted PIN blocks
  and delegates verification to the HSM pool.
- **DeviceManager owns physical outcome.** A transaction can be fully approved
  and still fail at dispense; that failure is a `DEV-` code and triggers a
  reversal from TransactionSwitch.
- **ConfigurationStore is read-only at runtime.** Components fetch configuration
  at startup and on a change notification; they never write it.

## Versioning

Components are released together as a platform version (currently `4.2`). The
running version of any component is reported by its health endpoint and by the
system version tool.
