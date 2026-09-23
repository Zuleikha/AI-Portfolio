---
document_id: payment-authorisation-api
title: Payment Authorisation API
domain: payments
component: PaymentEngine
version: "4.2"
doc_type: api
tags:
  - payments
  - api
  - authorisation
  - idempotency
---

# Payment Authorisation API

PaymentEngine exposes the payment authorisation API. This is the API used to
authorise a payment on the Meridian platform. All endpoints are versioned under
`/v1` and are served by PaymentEngine.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/payments/authorise` | Authorise a payment and reserve funds |
| `POST` | `/v1/payments/{payment_id}/capture` | Capture a previously authorised payment |
| `POST` | `/v1/payments/{payment_id}/reverse` | Reverse an authorisation or capture |
| `GET` | `/v1/payments/{payment_id}` | Retrieve current payment state |

Authorisation and capture are separate calls. An authorisation reserves funds;
it does not move them. Funds move on capture.

## POST /v1/payments/authorise

Request body:

```json
{
  "idempotency_key": "b8f1c2de-1f4a-4a19-9d2c-2c4a51d0f7a3",
  "account_id": "ACC-8842190",
  "instrument_token": "TOK-3f9a1c74e2",
  "amount": { "value": 125.00, "currency": "EUR" },
  "channel": "DIGITAL",
  "reference": "INV-2291"
}
```

Successful response, `201 Created`:

```json
{
  "payment_id": "PAY-2f7c9a1b",
  "status": "AUTHORISED",
  "authorised_amount": { "value": 125.00, "currency": "EUR" },
  "expires_at": "2026-09-15T10:22:00Z"
}
```

### Required headers

| Header | Purpose |
|---|---|
| `Authorization` | Bearer token issued to the calling service |
| `X-Request-Id` | Correlation id, echoed in every log entry for the call |
| `Content-Type` | `application/json` |

### Idempotency

`idempotency_key` is mandatory. PaymentEngine stores the key with the resulting
payment for `payments.idempotency_ttl_hours`.

- Replaying the same key with the same body returns the original response and
  does not authorise a second time.
- Replaying the same key with a different body returns `409 Conflict` with
  `PAY-8007`.

This is what makes a client-side retry after a network timeout safe.

## Status values

| Status | Meaning |
|---|---|
| `AUTHORISED` | Funds reserved, awaiting capture |
| `CAPTURED` | Funds moved |
| `DECLINED` | Authorisation refused |
| `REVERSED` | Authorisation released or capture refunded |
| `EXPIRED` | Authorisation lapsed before capture |

An authorisation that is not captured before `expires_at` moves to `EXPIRED` and
the reservation is released automatically.

## Error responses

| HTTP | Code | Meaning |
|---|---|---|
| `400` | `PAY-8001` | Request failed schema validation |
| `402` | `PAY-8003` | Authorisation declined by a downstream check |
| `409` | `PAY-8007` | Idempotency key reused with a different body |
| `422` | `PAY-8011` | Currency not supported for the account |
| `503` | `PAY-8020` | A downstream component was unavailable |

`PAY-8003` is a wrapper. The body carries a `decline_reason` holding the
underlying code from AuthorizationService, LimitService or CoreBankingAdapter
(for example `LIM-4001` or `COR-5003`), which is what identifies the actual
cause.

## Downstream calls

An authorisation call fans out to AuthorizationService (instrument checks),
LimitService (limit evaluation) and CoreBankingAdapter (funds reservation), in
that order. A failure in any one of them produces `PAY-8003`.
