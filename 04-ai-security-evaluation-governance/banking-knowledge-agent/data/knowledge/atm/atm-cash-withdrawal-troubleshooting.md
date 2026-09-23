---
document_id: atm-cash-withdrawal-troubleshooting
title: Troubleshooting a Failed Cash Withdrawal
domain: atm
component: TransactionSwitch
version: "4.2"
doc_type: troubleshooting
tags:
  - atm
  - withdrawal
  - troubleshooting
  - reversal
---

# Troubleshooting a Failed Cash Withdrawal

A procedure for diagnosing a single failed ATM cash withdrawal. Work through the
steps in order; each one narrows the failure to a smaller set of components.

## Step 1 - Get the transaction reference

Everything else depends on this. Obtain the `transaction_reference` from the
customer receipt, the terminal journal, or by searching transaction status with
the card token and an approximate time window. Without it, logs from nine
components cannot be correlated.

## Step 2 - Read the terminating error code

Look up the final error code recorded against the transaction. The code prefix
identifies the responsible component immediately.

| Prefix | Component | Means |
|---|---|---|
| `AUT-` | AuthorizationService | Card rejected before or during authentication |
| `CSM-` | CardSecurityModule | PIN or cryptogram verification problem |
| `LIM-` | LimitService | A configured limit was breached |
| `COR-` | CoreBankingAdapter | Funds or core banking problem |
| `DEV-` | DeviceManager | Hardware could not dispense |
| `SWX-` | TransactionSwitch | Timeout or orchestration failure |

## Step 3 - Establish how far the transaction got

Check which lifecycle stage last completed successfully.

- **Failed at stage 2 or 3** - the card or PIN was rejected. No debit occurred
  and no reversal is required. Move to the card authentication reference.
- **Failed at stage 4** - a limit blocked it. Check the configured limits for
  the account and the total consumed today. Limits are per account, so another
  card or another channel may have used the allowance.
- **Failed at stage 5** - either genuinely insufficient funds (`COR-5003`) or a
  core banking timeout (`COR-5008`). These look identical to the customer but
  are completely different faults. `COR-5008` is a platform incident,
  `COR-5003` is not.
- **Failed at stage 6 or 7** - the money was authorised but the hardware did
  not deliver. Go to step 4.
- **`SWX-7001`** - something downstream was too slow. Go to step 5.

## Step 4 - Money debited but no cash dispensed

This is the highest-priority customer-facing case.

1. Confirm the dispense outcome in the DeviceManager record for the terminal.
   `DEV-6009` (note count mismatch) means the dispenser and the counter
   disagree, and a physical cash reconciliation is required.
2. Confirm a reversal was generated (`SWX-7004`) against the same
   `transaction_reference`.
3. Confirm the reversal was acknowledged by CoreBankingAdapter. If it was
   retried `switch.reversal_retry_count` times without acknowledgement it is
   sitting in the reversal exception queue and will not resolve on its own.
   Raise it to operations for manual settlement.
4. Check the terminal for related device faults in the same period. A jam
   (`DEV-6004`) usually affects several consecutive transactions, not one.

## Step 5 - Diagnosing a switch timeout

`SWX-7001` names the switch, not the culprit. Filter the switch log by the
`transaction_reference` and find the downstream call whose duration approached
`switch.downstream_timeout_ms`. Then check that component's own health and
latency for the same period. A single slow transaction is usually a downstream
hiccup. A cluster of `SWX-7001` across many terminals is an incident, and the
incident response runbook applies.

## Step 6 - Confirm it is not terminal-specific

Check whether other transactions at the same terminal succeeded in the same
window.

- Only this terminal failing - suspect the device: cassette levels, dispenser
  state, network link. Check device status.
- Many terminals failing - suspect a shared component. Check the health of
  AuthorizationService, CardSecurityModule, LimitService and
  CoreBankingAdapter in that order, since that is the request path.

## What not to conclude

- A successful PIN entry does not mean the transaction should have completed.
  Four later stages can still reject it.
- A customer-visible "transaction declined" message does not identify the
  component. Only the error code does.
- Absence of a reversal record is not proof that no debit occurred. Confirm
  against CoreBankingAdapter rather than assuming.
