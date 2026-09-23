---
document_id: transaction-limits-configuration
title: Transaction Limits Configuration
domain: configuration
component: LimitService
version: "4.2"
doc_type: configuration
tags:
  - configuration
  - limits
  - atm
  - velocity
---

# Transaction Limits Configuration

LimitService evaluates every transaction against configured limits. This
document lists the configuration keys that control transaction limits, how they
combine, and how to interpret a limit rejection.

## The keys

| Key | Type | Default | Controls |
|---|---|---|---|
| `limits.atm.per_transaction_amount` | decimal | `500.00` | Largest single ATM withdrawal |
| `limits.atm.daily_withdrawal_amount` | decimal | `1000.00` | Total ATM withdrawal per day |
| `limits.atm.daily_withdrawal_count` | integer | `5` | Number of ATM withdrawals per day |
| `limits.atm.velocity_window_minutes` | integer | `60` | Sliding window for velocity checks |
| `limits.atm.velocity_max_transactions` | integer | `3` | Transactions allowed inside the window |
| `limits.digital.per_payment_amount` | decimal | `2500.00` | Largest single digital payment |
| `limits.digital.daily_payment_amount` | decimal | `5000.00` | Total digital payments per day |
| `limits.enforcement_mode` | enum | `strict` | `strict` rejects, `advisory` logs only |
| `limits.currency` | string | `EUR` | Currency all limit amounts are expressed in |

## Which key produced which rejection

| Code | Breached key |
|---|---|
| `LIM-4001` | `limits.atm.daily_withdrawal_amount` |
| `LIM-4002` | `limits.atm.per_transaction_amount` |
| `LIM-4003` | `limits.atm.daily_withdrawal_count` |
| `LIM-4005` | `limits.atm.velocity_max_transactions` |
| `LIM-4008` | `limits.digital.per_payment_amount` |
| `LIM-4009` | `limits.digital.daily_payment_amount` |

The error `details` object returns the limit and the consumed amount, which is
usually enough to explain the rejection without inspecting configuration.

## Precedence

Limits resolve in this order, most specific first:

1. **Account override** - a limit set explicitly on the account.
2. **Card product limit** - the limit attached to the card product.
3. **Platform default** - the value in the table above.

The first level that defines a key wins for that key. Levels are merged per key,
not wholesale: an account override for
`limits.atm.per_transaction_amount` does not discard the product's
`limits.atm.daily_withdrawal_amount`.

## Scope: account, not card

Every ATM limit is evaluated against the **account**, not the card. Two cards on
the same account share one daily allowance. This explains the common report that
a customer was refused on a card they had not used that day: the allowance was
consumed by another card or another channel on the same account.

Daily counters reset at midnight in the account's booking timezone, not at the
customer's local time or the terminal's.

## Velocity

Velocity is a sliding window, not a daily counter. Up to
`limits.atm.velocity_max_transactions` transactions are permitted in any
`limits.atm.velocity_window_minutes` period. A customer well inside their daily
allowance can still be stopped with `LIM-4005` for making several withdrawals in
quick succession.

## Enforcement mode

`limits.enforcement_mode` is `strict` in production. Setting it to `advisory`
makes LimitService evaluate and log breaches without rejecting, which is used
when tuning new limits. Advisory mode is a deliberate reduction in control and
is not a valid production setting.

## Changing a limit

Limit changes are applied through ConfigurationStore and take effect on the next
configuration refresh. Changes do not retroactively alter counters already
consumed today, so lowering a daily limit below what a customer has already
withdrawn simply blocks further withdrawals until the counter resets.
