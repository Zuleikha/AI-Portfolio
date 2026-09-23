---
document_id: api-integration-guide
title: Platform API Integration Guide
domain: api
component: Platform
version: "4.2"
doc_type: api
tags:
  - api
  - integration
  - authentication
  - errors
---

# Platform API Integration Guide

Conventions shared by every Meridian platform API. Component-specific endpoints
are documented separately; this guide covers the rules that apply to all of
them.

## Base URL and versioning

```
https://{environment}.meridian.internal/{component}/v1
```

Components expose their own path segment, for example `payments`, `cards`,
`limits`, `devices`, `config`. The major version is in the path. Breaking
changes get a new major version; additive changes do not.

## Authentication

Service-to-service calls use OAuth 2.0 client credentials. A caller exchanges
its client id and secret for a bearer token, then presents that token on every
request.

```
Authorization: Bearer <token>
```

Tokens are short-lived. Clients refresh before expiry rather than waiting for a
`401`. Credentials are supplied to a service through its environment; they are
never embedded in code, configuration files or repositories.

## Required headers

| Header | Required | Purpose |
|---|---|---|
| `Authorization` | Yes | Bearer token |
| `X-Request-Id` | Yes | Correlation id propagated through every downstream call |
| `Idempotency-Key` | On writes | Makes retries safe |
| `Content-Type` | On writes | `application/json` |

`X-Request-Id` is the single most useful field when tracing a failure across
components. A caller that does not send one gets one generated, but then cannot
correlate from its own side.

## Standard endpoints

| Method | Path | Component | Purpose |
|---|---|---|---|
| `POST` | `/payments/v1/payments/authorise` | PaymentEngine | Authorise a payment |
| `POST` | `/cards/v1/cards/authenticate` | AuthorizationService | Authenticate a card |
| `GET` | `/limits/v1/limits/{account_id}` | LimitService | Effective limits for an account |
| `GET` | `/devices/v1/devices/{terminal_id}/status` | DeviceManager | Terminal state and cassettes |
| `GET` | `/config/v1/config/{component}/{key}` | ConfigurationStore | Effective configuration value |
| `GET` | `/{component}/v1/health` | All | Liveness and version |

## Error format

Every component returns the same error envelope.

```json
{
  "error": {
    "code": "LIM-4001",
    "message": "Daily withdrawal limit exceeded",
    "request_id": "b8f1c2de-1f4a-4a19-9d2c-2c4a51d0f7a3",
    "details": { "limit": 500.00, "consumed": 500.00, "currency": "EUR" }
  }
}
```

The `code` is stable and safe to branch on. The `message` is for humans and may
change between releases, so clients should never match on its text.

## HTTP status conventions

| Status | Meaning |
|---|---|
| `200` / `201` | Success |
| `400` | Malformed request |
| `401` | Missing, expired or invalid token |
| `403` | Authenticated but not permitted |
| `404` | Resource does not exist |
| `409` | Conflict, typically an idempotency key reused with a different body |
| `422` | Well-formed but semantically rejected |
| `429` | Rate limited; honour `Retry-After` |
| `503` | Downstream unavailable; safe to retry with backoff |

## Retries

Retry `429` and `503` with exponential backoff and jitter. Do not retry `4xx`
other than `429`, since the request will fail identically. Always include the
original `Idempotency-Key` when retrying a write, otherwise a retry after a
network timeout can create a duplicate.

## Pagination

Collection endpoints use cursor pagination with `limit` and `cursor` query
parameters and return `next_cursor` when more results exist. Offset pagination
is not supported.
