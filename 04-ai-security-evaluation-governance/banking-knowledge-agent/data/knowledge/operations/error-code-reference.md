---
document_id: error-code-reference
title: Platform Error Code Reference
domain: operations
component: Platform
version: "4.2"
doc_type: reference
tags:
  - errors
  - codes
  - operations
  - troubleshooting
---

# Platform Error Code Reference

Every platform error code has the form `PREFIX-NNNN`. The prefix identifies the
component that raised it, so the code alone is enough to know where to look.

| Prefix | Component |
|---|---|
| `SWX` | TransactionSwitch |
| `AUT` | AuthorizationService |
| `CSM` | CardSecurityModule |
| `LIM` | LimitService |
| `COR` | CoreBankingAdapter |
| `PAY` | PaymentEngine |
| `DGW` | DigitalGateway |
| `DEV` | DeviceManager |
| `CFG` | ConfigurationStore |

The **class** column below separates codes that are normal business outcomes
from those that indicate a fault. Only the fault classes warrant an incident.

## AuthorizationService

| Code | Meaning | Class |
|---|---|---|
| `AUT-2001` | Card not found | Business |
| `AUT-2004` | Card blocked | Business |
| `AUT-2007` | Card expired | Business |
| `AUT-2012` | Card product not enabled for channel | Configuration |
| `AUT-2015` | Geographic restriction | Business |

## CardSecurityModule

| Code | Meaning | Class |
|---|---|---|
| `CSM-3002` | PIN verification failed | Business |
| `CSM-3005` | Invalid PIN block format | Configuration |
| `CSM-3007` | Cryptogram validation failed | Business or fraud |
| `CSM-3010` | HSM unavailable | Fault |
| `CSM-3014` | Key check value mismatch | Configuration |

## LimitService

| Code | Meaning | Class |
|---|---|---|
| `LIM-4001` | Daily withdrawal amount exceeded | Business |
| `LIM-4002` | Per-transaction amount exceeded | Business |
| `LIM-4003` | Daily withdrawal count exceeded | Business |
| `LIM-4005` | Velocity limit exceeded | Business |
| `LIM-4008` | Digital per-payment amount exceeded | Business |
| `LIM-4009` | Digital daily payment amount exceeded | Business |

## CoreBankingAdapter

| Code | Meaning | Class |
|---|---|---|
| `COR-5003` | Insufficient funds | Business |
| `COR-5006` | Account blocked or dormant | Business |
| `COR-5008` | Core banking timeout | Fault |
| `COR-5011` | Core banking rejected the posting | Fault |
| `COR-5015` | Connection pool exhausted | Fault |

## TransactionSwitch

| Code | Meaning | Class |
|---|---|---|
| `SWX-7001` | Downstream timeout | Fault |
| `SWX-7004` | Reversal generated | Informational |
| `SWX-7006` | Reversal unacknowledged after retries | Fault |
| `SWX-7009` | Unroutable transaction type | Configuration |

## DeviceManager

| Code | Meaning | Class |
|---|---|---|
| `DEV-6002` | Cassette empty | Operational |
| `DEV-6004` | Dispenser jam | Fault |
| `DEV-6009` | Note count mismatch | Fault |
| `DEV-6011` | Notes presented but not taken | Operational |

## PaymentEngine

| Code | Meaning | Class |
|---|---|---|
| `PAY-8001` | Request validation failed | Client |
| `PAY-8003` | Authorisation declined | Wrapper |
| `PAY-8007` | Idempotency key conflict | Client |
| `PAY-8011` | Currency not supported | Configuration |
| `PAY-8020` | Downstream unavailable | Fault |

## DigitalGateway

| Code | Meaning | Class |
|---|---|---|
| `DGW-9002` | Session expired | Business |
| `DGW-9004` | Session token invalid | Business |
| `DGW-9006` | Step-up authentication required | Informational |
| `DGW-9009` | Rate limit exceeded | Client |
| `DGW-9012` | Channel disabled | Configuration |
| `DGW-9014` | Client version unsupported | Client |

## Wrapper codes

`PAY-8003` is a wrapper: it reports that something declined the payment, not
what. Read the `decline_reason` in the response body for the underlying code.
Treating `PAY-8003` itself as the cause is the most common diagnostic mistake in
the payments domain.

`SWX-7001` is similar. It names TransactionSwitch, but the fault is nearly
always in whichever downstream component was slow.
