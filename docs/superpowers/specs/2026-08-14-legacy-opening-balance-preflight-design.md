# Legacy Opening Balance Preflight - Design

Date: 2026-08-14
Status: approved for implementation

## Problem

The corrective replacement preflight accepts only `source='actual'` transactions
whose descriptions identify an Actual blob transaction. Historical imports also
created synthetic opening-balance rows. They have no Actual identifier, so the
otherwise safe correction fails before it can replace the legacy import.

## Decision

Treat an unmatched transaction as a synthetic opening balance only when all of
the following are true:

- its source is `actual`;
- its description starts exactly with `[BO] Bilans otwarcia`;
- it has exactly two postings;
- both postings reference the same non-null account;
- neither posting references a category; and
- their signed values are equal and opposite.

The preflight will accept this narrow legacy shape while retaining its account
as a deletion candidate. Every other unmatched Actual transaction remains a
`LegacyActualMappingError`; manual transactions are never accepted by this
exception.

## Testing

Unit tests establish the allowed BO record and prove rejection of a prefix
lookalike, a manually sourced BO record, an imbalanced BO record, a categorized
record, and postings from different accounts. The existing replacement safety
tests continue to cover ordinary unmatched Actual provenance and manual
references.
