# NBP Weekend FX Fallback Design

## Goal

Allow the Actual importer to use the last NBP Table A USD/EUR rate published before a Saturday or Sunday transaction date, while retaining the published effective date and an explicit provenance label.

## Scope

- Keep the exact-date Table A request as the primary lookup.
- Only an HTTP 404 for a Saturday or Sunday triggers a bounded historical range request ending on the requested date.
- Use the newest response rate whose `effectiveDate` is earlier than the requested date.
- Cache the complete quote by requested currency/date: numeric rate, effective date, and source.
- Propagate the quote provenance to imported postings as `nbp_previous_business_day`.
- Preserve failure for non-weekend missing rates and for a weekend range with no usable published rate.

## Exclusions

- No production PA database access, Actual write API access, schema migration, or general holiday fallback.
- No synthetic rate, `1.0` fallback, or manual correction.

## Data Flow

`NbpRateProvider` returns an immutable quote instead of a bare float. An exact response produces source `nbp`; a validated weekend range response produces `nbp_previous_business_day`. The importer keeps quotes in its FX lookup map and uses the quote's rate and source when constructing postings. An unavailable lookup remains unavailable and raises the existing `ImportValidationError`.

## Tests

- Saturday and Sunday exact-date 404s use the latest response rate from the fallback range and expose Friday as the effective date.
- The quote is cached under the requested weekend date, retaining its source and effective date.
- A no-rate weekend range remains unavailable and is not cached.
- Import postings retain `nbp_previous_business_day` rather than `nbp` or `1.0`.
