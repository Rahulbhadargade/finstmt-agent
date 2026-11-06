# Manual adjustments report - 2024-Q4

Run ID: `f846bb2bfe8cf962`  |  Functional currency: USD

## Outcome

| Entry | Description | Amount | Decision | Why |
|---|---|---:|---|---|
| JE-001 | Accrue Q4 bonus pool | $850,000.00 | ⚠️ ACCEPTED_WITH_WARNINGS | Above review threshold |
| JE-002 | Reclassify marketing spend wrongly booked to T&E | $28,500.00 | ❌ REJECTED | Debits do not equal credits |
| JE-003 | FX revaluation of EUR cash balance to period-end rate | $11,200.00 | ⏸️ QUARANTINED | FX revaluation amount does not reconcile |
| JE-004 | Bad debt provision top-up | $45,000.00 | ✅ ACCEPTED | - |
| JE-005 | Reclass conference travel from old code | $18,500.00 | ⏸️ QUARANTINED | Account 6315 is not in the chart of accounts |
| JE-006 | Depreciation catch-up — Q4 | $215,000.00 | ⏸️ QUARANTINED | Possible duplicate depreciation |
| JE-007 | Deferred tax true-up | $38,000.00 | ✅ ACCEPTED | - |
| JE-008 | Intercompany settlement — UK sub | $320,000.00 | ❌ REJECTED | Entry nets to zero (circular) |
| JE-009 | Accrue legal fees for ongoing litigation | $75,000.00 | ✅ ACCEPTED | - |
| JE-010 | Reclass long-term debt current portion | $200,000.00 | ✅ ACCEPTED | - |

Counts: ACCEPTED 4, ACCEPTED_WITH_WARNINGS 1, QUARANTINED 3, REJECTED 2

## Effect of posted entries (as-reported amounts, no FX translation)

- Net income before adjustments: $6,006,500.00
- Net income after posted entries: $4,998,500.00 (change -$1,008,000.00)
- TB debits minus credits before: -$4,800.00; after: -$4,800.00 (posted entries are balanced, so the pre-existing difference is unchanged and still unexplained)

## Entry by entry

### JE-001 - Accrue Q4 bonus pool  ⚠️ ACCEPTED_WITH_WARNINGS

Date 2024-12-31 | Source: Finance team — bonus accrual workbook v3

Posted, with points you should know about. At $850,000.00 this entry is at or above the $500,000.00 review threshold. It was posted, but an approver should sign it off. Next step: Get approver sign-off and attach the supporting workbook.

Checks: R01=pass, R02=pass, R03=pass, R04=pass, R05=pass, R06=pass, R07=pass, R08=pass, R09=fail, R10=pass, R11=pass

### JE-002 - Reclassify marketing spend wrongly booked to T&E  ❌ REJECTED

Date 2024-12-28 | Source: Controller note 2024-12-28

Rejected. Not posted. Debits total $28,500.00 but credits total $25,000.00, so the entry is out of balance by $3,500.00. Posting it would break the trial balance. Next step: Ask the preparer (Controller note 2024-12-28) which amount is correct and resubmit. Nothing was posted and nothing was auto-corrected.

Checks: R01=pass, R02=fail, R03=pass, R04=pass, R05=pass, R06=pass, R07=pass, R08=pass, R09=pass, R10=pass, R11=pass

### JE-003 - FX revaluation of EUR cash balance to period-end rate  ⏸️ QUARANTINED

Date 2024-12-31 | Source: FX reval calc

On hold for your decision. Not posted. The entry revalues EUR cash by $11,200.00. Recomputing from the EUR balance (EUR 825,400.00) and the rates file gives average-to-closing rate: $10,730.20; opening-to-closing rate: $19,809.60. The entry matches neither (within 1%). GBP cash of 412,300.00 also needs revaluation, but there is no GBP period-end rate, so this entry covers EUR only. Next step: Ask the preparer which rates and balance were used, or approve it explicitly if the difference is understood. Provide the GBP period-end rate.

Checks: R01=pass, R02=pass, R03=pass, R04=pass, R05=pass, R06=pass, R07=fail, R08=pass, R09=pass, R10=pass, R11=pass

### JE-004 - Bad debt provision top-up  ✅ ACCEPTED

Date 2024-12-31 | Source: AR aging review

Passed all checks and was posted.

Checks: R01=pass, R02=pass, R03=pass, R04=pass, R05=pass, R06=pass, R07=pass, R08=pass, R09=pass, R10=pass, R11=pass

### JE-005 - Reclass conference travel from old code  ⏸️ QUARANTINED

Date 2024-12-15 | Source: AP team

On hold for your decision. Not posted. Line 1 posts $18,500.00 to account 6315, which does not exist in the COA (memo: 'Conf travel'). The closest existing accounts are listed as suggestions only; none were applied. Note: mapping 6315 to 6310 would make this entry post to the same account on both sides (net zero), so the real fix is probably a new COA account, not a remap. Next step: Either add the account to the COA or tell me which existing account to use; then the entry is re-checked.

Suggested accounts (not applied):
- 6310 Travel and Entertainment (confidence 0.72)
- 6300 Marketing and Advertising (confidence 0.46)
- 6500 Depreciation Expense (confidence 0.10)

Checks: R01=pass, R02=pass, R03=fail, R04=pass, R05=pass, R06=pass, R07=pass, R08=pass, R09=pass, R10=pass, R11=pass

### JE-006 - Depreciation catch-up — Q4  ⏸️ QUARANTINED

Date 2024-12-31 | Source: Fixed asset register

On hold for your decision. Not posted. Accumulated depreciation already grew by $850,000.00 since the prior period, which equals the depreciation expense already in the TB ($850,000.00). Adding $215,000.00 more may double count. Next step: Check the fixed asset register: is this amount incremental to what the TB already contains?

Checks: R01=pass, R02=pass, R03=pass, R04=pass, R05=pass, R06=pass, R07=pass, R08=fail, R09=pass, R10=pass, R11=pass

### JE-007 - Deferred tax true-up  ✅ ACCEPTED

Date 2024-12-31 | Source: Tax provision memo

Passed all checks and was posted.

Checks: R01=pass, R02=pass, R03=pass, R04=pass, R05=pass, R06=pass, R07=pass, R08=pass, R09=pass, R10=pass, R11=pass

### JE-008 - Intercompany settlement — UK sub  ❌ REJECTED

Date 2024-12-30 | Source: IC reconciliation

Rejected. Not posted. Every line posts to the same account(s) (2170) and cancels out: $320,000.00 is debited and credited to the same place, so the entry changes nothing. Intercompany settlements need a different account on each side (for example cash against the intercompany payable). Next step: Ask the preparer for the intended counter-account (usually cash or the intercompany receivable) and resubmit.

Checks: R01=pass, R02=pass, R03=pass, R04=fail, R05=pass, R06=pass, R07=pass, R08=pass, R09=pass, R10=pass, R11=fail

### JE-009 - Accrue legal fees for ongoing litigation  ✅ ACCEPTED

Date 2024-12-31 | Source: Legal memo dated 2024-12-29

Passed all checks and was posted.

Checks: R01=pass, R02=pass, R03=pass, R04=pass, R05=pass, R06=pass, R07=pass, R08=pass, R09=pass, R10=pass, R11=pass

### JE-010 - Reclass long-term debt current portion  ✅ ACCEPTED

Date 2024-12-31 | Source: Treasury schedule

Passed all checks and was posted.

Checks: R01=pass, R02=pass, R03=pass, R04=pass, R05=pass, R06=pass, R07=pass, R08=pass, R09=pass, R10=pass, R11=pass

## Problems found in the input files

| ID | Severity | Finding |
|---|---|---|
| DQ-01 | BLOCK | Trial balance does not balance. Total debits $71,072,200.00 vs total credits $71,077,000.00: difference -$4,800.00 (as reported, before any FX translation). Not forced to balance; this must be explained, not plugged. |
| DQ-02 | REVIEW | Account 6310 appears 2 times in USD. Rows line 48 ($245,000.00), line 49 ($38,500.00). They are summed here, but one may be a duplicate export row. |
| DQ-03 | REVIEW | Account 9999 'Suspense - Unmapped' is not in the COA (trial_balance). Line 63 carries $12,400.00 on an account with no COA mapping. |
| DQ-03 | REVIEW | Account 6905 'Sundry Operating Expenses' is not in the COA (prior_period_tb). Line 34 carries $132,000.00 on an account with no COA mapping. Possible match (suggestion only): 6900 'Other Operating Expenses', confidence 0.81. |
| DQ-04 | REVIEW | No period_end FX rate for GBP. GBP balances exist in the TB but fx_rates.csv has no period_end rate. Translation and revaluation for GBP cannot be verified. |
| DQ-05 | WARN | COA account 1150 'Other Current Assets' has cash-flow category TBD. The cash-flow statement cannot classify this account until a category is chosen. |
| DQ-05 | INFO | COA header 1290 'Other Assets' has no child accounts. Nothing maps under it. |
| DQ-05 | WARN | COA account 2170 'Intercompany Payable' has cash-flow category TBD. The cash-flow statement cannot classify this account until a category is chosen. |
| DQ-05 | INFO | COA header 7000 has no normal balance. Harmless for a header. |
| DQ-06 | WARN | Prior-period TB has almost no P&L accounts. It looks post-close (balance sheet only), but one P&L-style account (6905) is present. Retained earnings moved without a visible closing entry; confirm pre- vs post-close. |
