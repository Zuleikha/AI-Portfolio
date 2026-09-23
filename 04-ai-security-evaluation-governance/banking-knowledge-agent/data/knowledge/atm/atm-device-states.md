---
document_id: atm-device-states
title: ATM Device States and Cash Handling
domain: atm
component: DeviceManager
version: "4.2"
doc_type: reference
tags:
  - atm
  - device
  - cassette
  - dispenser
---

# ATM Device States and Cash Handling

DeviceManager tracks the physical state of every ATM terminal and decides
whether a terminal may accept transactions. TransactionSwitch consults it before
routing a withdrawal and instructs it to dispense afterwards.

## Terminal states

| State | Accepts transactions | Meaning |
|---|---|---|
| `IN_SERVICE` | Yes | Fully operational |
| `DEGRADED` | Yes, restricted | Operational but at least one cassette is low or a non-critical device has faulted |
| `SUPERVISOR` | No | An engineer or cash-replenishment team holds the terminal |
| `OUT_OF_SERVICE` | No | A critical fault, or manually withdrawn from service |
| `UNREACHABLE` | No | No heartbeat received within `device.heartbeat_timeout_seconds` |

A terminal in `DEGRADED` still serves customers, but withdrawal amounts that
cannot be composed from the remaining denominations are rejected before
authorisation rather than at dispense.

## Cassettes and denominations

Each terminal has four cassettes. DeviceManager holds a note count per cassette
and recalculates the dispensable amount set whenever a count changes.

- A cassette below `device.cassette_low_threshold` marks the terminal
  `DEGRADED`.
- A cassette at zero raises `DEV-6002` for any amount that requires that
  denomination.
- If the requested amount cannot be composed from available denominations, the
  terminal offers the nearest dispensable amounts instead of failing.

Counts are updated by replenishment, by each successful dispense, and by
reconciliation after a fault.

## Dispense outcomes

| Outcome | Code | Meaning | Reversal |
|---|---|---|---|
| Dispensed | - | Notes presented and taken | No |
| Cassette empty | `DEV-6002` | Denomination unavailable | Yes |
| Dispenser jam | `DEV-6004` | Mechanical failure mid-dispense | Yes |
| Note count mismatch | `DEV-6009` | Counter and dispenser disagree | Yes, plus reconciliation |
| Notes not taken | `DEV-6011` | Presented but retracted after timeout | Yes |

Every outcome other than a clean dispense triggers a reversal from
TransactionSwitch, because authorisation has already debited the account.

`DEV-6009` is the only outcome that cannot be resolved from the platform alone:
the discrepancy must be settled against the physical cash count from the next
replenishment.

## Heartbeats and health

Terminals send a heartbeat every `device.heartbeat_interval_seconds`. Missing
heartbeats for longer than `device.heartbeat_timeout_seconds` moves a terminal
to `UNREACHABLE`. This is a network or power symptom rather than a platform
fault, and a terminal usually recovers on its own once the link returns.

A cluster of terminals going `UNREACHABLE` at the same moment normally points at
shared network infrastructure, not at DeviceManager.

## What DeviceManager does not do

- It does not authorise transactions. A dispense instruction reaching
  DeviceManager has already been approved by AuthorizationService, LimitService
  and CoreBankingAdapter.
- It does not generate reversals. It reports the dispense outcome, and
  TransactionSwitch decides.
- It does not hold card or customer data, only terminal identifiers and device
  state.
