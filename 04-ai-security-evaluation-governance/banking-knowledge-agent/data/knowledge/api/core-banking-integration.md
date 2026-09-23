---
document_id: core-banking-integration
title: Core Banking Integration
domain: api
component: CoreBankingAdapter
version: "4.2"
doc_type: reference
tags:
  - integration
  - core-banking
  - ledger
  - timeouts
---

# Core Banking Integration

CoreBankingAdapter is the only component permitted to talk to the core banking
system. Every balance enquiry, debit, credit and reversal from any channel
passes through it. Nothing else holds a core banking connection.

## Why a single adapter

Concentrating core banking access in one component means connection pooling,
timeout policy, retry behaviour and message translation exist once rather than
in every channel. It also means the core banking system can be replaced by
changing one component, which is the main reason the boundary exists.

## Operations

| Operation | Purpose | Idempotent |
|---|---|---|
| `balance_enquiry` | Available and ledger balance for an account | Yes |
| `reserve_funds` | Hold an amount against available balance | Yes, on reference |
| `post_debit` | Move funds out of the account | Yes, on reference |
| `post_credit` | Move funds into the account | Yes, on reference |
| `release_reservation` | Cancel a hold | Yes, on reference |

Every write carries the originating `transaction_reference`. Re-sending the same
reference does not double-post, which is what makes reversal retries safe.

## Available balance versus ledger balance

These are different numbers and confusing them causes most balance disputes.

- **Ledger balance** is the settled position.
- **Available balance** is the ledger balance minus active reservations, plus
  any agreed overdraft.

`COR-5003` (insufficient funds) is evaluated against available balance. A
customer can therefore be refused while their ledger balance appears sufficient,
because an uncaptured authorisation is still holding part of it.

## Timeouts and pooling

| Key | Default | Effect |
|---|---|---|
| `core.request_timeout_ms` | `5000` | Individual core call budget |
| `core.connection_pool_size` | `40` | Concurrent connections held |

When the core banking system slows down, the failure sequence is predictable:
latency rises, connections are held longer, the pool saturates (`COR-5015`),
then calls start timing out (`COR-5008`). Seeing `COR-5015` and `COR-5008`
together means the core is slow, not that the adapter is broken.

Because `switch.downstream_timeout_ms` wraps these calls, a slow core also
produces `SWX-7001` at the switch and reversals for anything already
authorised.

## Error codes

| Code | Meaning | Retryable |
|---|---|---|
| `COR-5003` | Insufficient funds | No |
| `COR-5006` | Account blocked or dormant | No |
| `COR-5008` | Core banking timeout | Yes, with the same reference |
| `COR-5011` | Core banking rejected the posting | No, investigate |
| `COR-5015` | Connection pool exhausted | Yes, with backoff |

`COR-5008` is ambiguous by nature: the adapter does not know whether the core
applied the posting before the timeout. This is exactly why every write is
idempotent on the transaction reference, and why the resolution is to retry or
reverse with the same reference rather than to issue a new one.

## What the adapter does not do

- It does not evaluate limits. That is LimitService.
- It does not decide whether a card may be used. That is AuthorizationService.
- It does not generate reversals. It executes them when TransactionSwitch or
  PaymentEngine asks.
