---
document_id: incident-response-runbook
title: Incident Response Runbook
domain: operations
component: Platform
version: "4.2"
doc_type: runbook
tags:
  - incident
  - operations
  - runbook
  - severity
---

# Incident Response Runbook

Procedure for handling a platform incident affecting transaction processing.
Individual customer complaints are not incidents; use the withdrawal
troubleshooting procedure for those.

## Severity

| Severity | Criteria | Response |
|---|---|---|
| `SEV1` | Transactions failing across multiple channels, or cash at risk | Immediate, all hands |
| `SEV2` | One channel or one component degraded, customers affected | Immediate, owning team |
| `SEV3` | Elevated errors, no customer impact yet | Next business hours |
| `SEV4` | Single terminal or isolated fault | Scheduled |

Cash discrepancy (`DEV-6009` at volume) and unacknowledged reversals
(`SWX-7006`) are always at least `SEV2` regardless of transaction volume,
because money is unaccounted for.

## Step 1 - Establish blast radius

Before diagnosing, determine the shape of the failure.

| Observation | Likely location |
|---|---|
| One terminal | Device or local network |
| Terminals in one region | Regional network or a terminal group configuration |
| All ATM, digital unaffected | TransactionSwitch or DeviceManager |
| All digital, ATM unaffected | DigitalGateway |
| ATM and digital simultaneously | A shared component: AuthorizationService, CardSecurityModule, LimitService or CoreBankingAdapter |

Failures in both ATM and digital at once are the strongest signal available.
They rule out the channel components entirely and point at the shared path.

## Step 2 - Identify the dominant error code

Group failures in the window by error code and take the most frequent one. Then
apply the class from the error code reference:

- **Business class** rising sharply is rarely a platform fault. It is usually a
  configuration change, for example a limit lowered by mistake producing a wave
  of `LIM-4001`.
- **Fault class** points at the named component.
- **Configuration class** points at a recent change. Check the configuration
  version history for that component first.

## Step 3 - Check for a recent change

Most incidents follow a change. Before deep investigation, check for:

- A configuration version applied to the affected component in the last 24
  hours.
- A platform deployment.
- A key rotation, which produces `CSM-3014` on affected terminals.
- A terminal deployment or firmware update, which produces `CSM-3005`.

If a change correlates with the start of the incident, rolling that change back
is usually faster than diagnosing forward. ConfigurationStore versions are
immutable, so rollback is re-applying the previous version id.

## Step 4 - Component checks

Check in request-path order, since a failure upstream masks everything below it.

1. TransactionSwitch or DigitalGateway health and latency.
2. AuthorizationService decision rate and latency.
3. CardSecurityModule HSM pool saturation. Rising authentication latency
   precedes `CSM-3010` and is the earlier warning.
4. LimitService evaluation latency.
5. CoreBankingAdapter timeout rate and connection pool usage. `COR-5015`
   (pool exhausted) and `COR-5008` (timeout) usually appear together when the
   core is slow.

## Step 5 - Protect the money

Independently of root cause, for any incident involving ATM withdrawals:

1. Query the reversal exception queue for `SWX-7006`.
2. Reconcile `DEV-6009` occurrences against the physical cash count at the next
   replenishment.
3. Record affected `transaction_reference` values before logs age out.

This step is not deferred until after resolution. Reversal and reconciliation
evidence is time-limited, and recovering it later is significantly harder.

## Step 6 - Recovery and closure

Confirm recovery on the same signal used to detect the incident, not on the
absence of alerts. Then record: timeline, dominant error codes, blast radius,
the change involved if any, customer impact, and any unresolved reversals or
cash discrepancies carried forward.
