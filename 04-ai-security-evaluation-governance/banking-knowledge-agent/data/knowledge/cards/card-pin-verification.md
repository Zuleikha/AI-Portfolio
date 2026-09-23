---
document_id: card-pin-verification
title: PIN Verification and the Card Security Module
domain: cards
component: CardSecurityModule
version: "4.2"
doc_type: reference
tags:
  - cards
  - pin
  - hsm
  - security
---

# PIN Verification and the Card Security Module

CardSecurityModule (CSM) performs every cryptographic operation involving card
data. It sits between AuthorizationService and the hardware security module
(HSM) pool, and it is the only component permitted to talk to the HSMs.

## Responsibilities

- Translate encrypted PIN blocks between the terminal key and the issuer key.
- Verify PIN blocks against the stored PIN verification value.
- Validate EMV application cryptograms (ARQC) and generate response
  cryptograms (ARPC).
- Manage key rotation and key check values for terminal and issuer keys.

CSM never receives, holds or logs a clear PIN. A PIN block arrives encrypted
under one key and is translated inside the HSM to another; the clear value never
exists in application memory.

## Error codes

| Code | Meaning | Usual cause |
|---|---|---|
| `CSM-3002` | PIN verification failed | Wrong PIN entered |
| `CSM-3005` | Invalid PIN block format | Terminal and platform disagree on PIN block format |
| `CSM-3007` | Cryptogram validation failed | Cloned or faulty chip, or a key mismatch |
| `CSM-3010` | HSM unavailable | No HSM in the pool answered within the timeout |
| `CSM-3014` | Key check value mismatch | Terminal key rotated without matching platform update |

## Distinguishing a wrong PIN from a platform fault

This distinction matters more than any other in this component.

- `CSM-3002` is a normal business outcome. The customer entered the wrong PIN.
  It increments the card's PIN retry counter and, at
  `cards.pin_retry_limit`, blocks the card.
- `CSM-3005` and `CSM-3014` are configuration or key management faults. They
  affect every transaction from an affected terminal or terminal group, not one
  customer. A rise in these codes after a terminal deployment almost always
  means a key or format mismatch introduced by that deployment.
- `CSM-3010` is an availability incident. Nothing is wrong with the card.

A support case reporting "my PIN is not accepted" is only a `CSM-3002` case if
the code confirms it. `CSM-3005` produces the same customer experience with a
completely different cause.

## The HSM pool

CSM maintains a pool of `csm.hsm_pool_size` connections. Requests are issued to
the pool with a timeout of `csm.hsm_request_timeout_ms`.

- If the pool is exhausted, requests queue. Queueing shows up first as rising
  authentication latency, and only later as `CSM-3010`.
- If no HSM answers, CSM raises `CSM-3010` and AuthorizationService declines the
  transaction. There is no fallback path that skips verification, by design.
- Because CSM sits on the critical path of every card transaction, HSM
  saturation presents as a platform-wide failure across ATM and digital
  channels simultaneously. That combination is a strong signal for CSM rather
  than for any single channel.

## Key rotation

Terminal keys are rotated on a schedule and on demand. A rotation requires the
terminal and the platform to be updated together. Rotating one side alone
produces `CSM-3014` on every subsequent transaction at that terminal, so
rotation is verified with a test transaction before the terminal returns to
service.
