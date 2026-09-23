---
document_id: configuration-reference
title: Platform Configuration Reference
domain: configuration
component: ConfigurationStore
version: "4.2"
doc_type: configuration
tags:
  - configuration
  - timeouts
  - operations
---

# Platform Configuration Reference

ConfigurationStore holds versioned configuration for every component and
distributes it. This document covers how configuration is applied and lists the
operational keys outside the limits domain.

## How configuration is applied

Components read configuration at startup and on a change notification. There is
no polling and no runtime write path: components consume configuration, they
never modify it.

Every change creates a new configuration version. Versions are immutable, so a
rollback is a redeploy of an earlier version rather than an edit.

| Property | Behaviour |
|---|---|
| Scope | Per component, per environment |
| Change effect | Applied on next refresh notification |
| Rollback | Re-apply a previous version id |
| Audit | Every version records author, timestamp and change reason |

## Reading an effective value

```
GET /config/v1/config/{component}/{key}
```

The response returns the value actually in effect, the version it came from, and
the precedence level that supplied it. This is the authoritative answer when a
component appears not to be honouring a change: the change may exist in a newer
version that the component has not yet refreshed to.

## Timeout and retry keys

| Key | Component | Default | Controls |
|---|---|---|---|
| `switch.downstream_timeout_ms` | TransactionSwitch | `8000` | End-to-end budget for one transaction |
| `switch.reversal_retry_count` | TransactionSwitch | `3` | Reversal attempts before the exception queue |
| `core.request_timeout_ms` | CoreBankingAdapter | `5000` | Core banking call timeout |
| `core.connection_pool_size` | CoreBankingAdapter | `40` | Concurrent core banking connections |
| `csm.hsm_pool_size` | CardSecurityModule | `8` | HSM connections held |
| `csm.hsm_request_timeout_ms` | CardSecurityModule | `2000` | Per-HSM-request timeout |
| `payments.idempotency_ttl_hours` | PaymentEngine | `24` | How long an idempotency key is remembered |
| `payments.authorisation_validity_hours` | PaymentEngine | `168` | Before an authorisation expires |
| `payments.clearing_retry_count` | PaymentEngine | `3` | Batch submission attempts |

`switch.downstream_timeout_ms` must remain larger than the sum of the timeouts
it wraps. Setting it below `core.request_timeout_ms` means the switch abandons
transactions the core would have completed, converting a slow path into a stream
of `SWX-7001` failures and unnecessary reversals.

## Card and channel keys

| Key | Component | Default | Controls |
|---|---|---|---|
| `cards.pin_retry_limit` | AuthorizationService | `3` | PIN attempts before the card blocks |
| `cards.allow_stripe_fallback` | AuthorizationService | `false` | Magnetic-stripe fallback |
| `digital.session_ttl_minutes` | DigitalGateway | `30` | Session lifetime |
| `digital.session_idle_timeout_minutes` | DigitalGateway | `10` | Inactivity cutoff |
| `digital.step_up_amount_threshold` | DigitalGateway | `1000.00` | Amount requiring step-up |
| `digital.rate_limit_per_session` | DigitalGateway | `60` | Requests per minute per session |
| `digital.rate_limit_per_account` | DigitalGateway | `120` | Requests per minute per account |
| `digital.minimum_client_version` | DigitalGateway | `5.8.0` | Oldest supported mobile client |

## Device keys

| Key | Component | Default | Controls |
|---|---|---|---|
| `device.heartbeat_interval_seconds` | DeviceManager | `30` | Terminal heartbeat frequency |
| `device.heartbeat_timeout_seconds` | DeviceManager | `120` | Before a terminal is `UNREACHABLE` |
| `device.cassette_low_threshold` | DeviceManager | `150` | Note count that marks a terminal `DEGRADED` |

## Secrets are not configuration

ConfigurationStore holds operational values only. Credentials, API keys and
cryptographic keys are supplied to components through their runtime environment
and secret management, never through configuration versions, and never appear in
a configuration response or audit record.
