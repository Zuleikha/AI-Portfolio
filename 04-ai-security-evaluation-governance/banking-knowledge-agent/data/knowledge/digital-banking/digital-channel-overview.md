---
document_id: digital-channel-overview
title: Digital Banking Channel Overview
domain: digital-banking
component: DigitalGateway
version: "4.2"
doc_type: reference
tags:
  - digital-banking
  - mobile
  - session
  - gateway
---

# Digital Banking Channel Overview

DigitalGateway is the entry point for mobile and web banking. It terminates
customer sessions, validates requests, and forwards work to PaymentEngine,
AuthorizationService and CoreBankingAdapter. It holds no business logic of its
own.

## What the gateway does

| Responsibility | Detail |
|---|---|
| Session management | Issues and validates session tokens, enforces inactivity timeout |
| Step-up authentication | Requests additional verification for sensitive operations |
| Request shaping | Translates channel requests into internal service calls |
| Rate limiting | Per-session and per-account request ceilings |
| Response filtering | Removes internal fields before responding to the client |

## Sessions

A session is created after customer login and carries a token with a lifetime of
`digital.session_ttl_minutes`. Inactivity beyond
`digital.session_idle_timeout_minutes` ends it early.

| Code | Meaning |
|---|---|
| `DGW-9002` | Session expired |
| `DGW-9004` | Session token invalid or revoked |
| `DGW-9006` | Step-up authentication required |
| `DGW-9009` | Rate limit exceeded |
| `DGW-9012` | Channel disabled for this account or product |

`DGW-9006` is not a failure. It is an instruction to the client to collect a
second factor and retry with the resulting assertion.

## Step-up authentication

Certain operations always require step-up regardless of session age:

- Adding or amending a payee.
- Payments above `digital.step_up_amount_threshold`.
- Changing limits or contact details.
- First payment to a new destination.

The gateway returns `DGW-9006` with a challenge reference. The client completes
the challenge and repeats the original request including the assertion.

## Relationship to the other components

DigitalGateway does not authorise payments and does not evaluate limits. It
forwards to PaymentEngine, which fans out to AuthorizationService, LimitService
and CoreBankingAdapter exactly as it does for any other caller.

This matters when diagnosing a failed digital payment: a `DGW-` code is a
channel or session problem, while a `PAY-`, `LIM-`, `AUT-` or `COR-` code is a
payment problem that happens to have arrived through the digital channel. The
same limits apply whether a customer uses an ATM or the mobile app, because
LimitService evaluates against the account.

## Rate limiting

The gateway applies two ceilings, `digital.rate_limit_per_session` and
`digital.rate_limit_per_account`, both per minute. Exceeding either returns
`DGW-9009` with a `Retry-After` header. Rate limiting protects the components
behind the gateway from a misbehaving client, so raising these ceilings is a
change that needs care rather than a routine tuning knob.

## Client compatibility

The gateway supports the current and previous mobile application versions.
Requests from older versions receive `DGW-9014` and a prompt to update. The
supported window is controlled by `digital.minimum_client_version`.
