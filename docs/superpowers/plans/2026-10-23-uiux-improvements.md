# UI/UX improvements — approved scope

User approved audit and visual direction in conversation. No API/backend changes or deploy.

- [x] Mobile account/category identity separate from actions, wrapped long names.
- [x] 44px touch targets for sidebar and scoped forms/calendar/upload controls.
- [x] Accessible loading/error/retry in finance overview and transaction reference data.
- [x] Compact mobile calendar agenda retaining every visible day and entry.
- [x] Today: actions and chronological day plan before secondary counts; explicit current block.
- [x] Scoped theme: ink #101C2C, surface #192A3D, border #344B61, text #EDF3F8,
  muted #AEC0CF, accent #78B9DE. Preserve error/warning semantics and focus visibility.
- [x] Local Barlow Semi Condensed headings and Source Sans 3 body with licenses.
- [x] TDD where behavior changes; browser screenshots desktop/mobile; tests/lint/types/build.
- [x] Independent review and docs; local commit only, no merge/push/deploy without approval.

Audit baseline: eight synthetic screenshots in /tmp/opencode/uiux-audit. Mobile
account name collapsed, actions34px; calendar controls32px and oversized empty days.
Implementation must not rely only on document scrollWidth: verify individual bounds.

Final evidence: backend642 PASS (8 proxy deselected), frontend194 PASS, E2E29 PASS
and 1 intentional skip (mobile-only agenda on desktop). Ruff/mypy/ESLint/tsc/build/
diff PASS. Axe on four screens x2 viewport: no violations in selected WCAG A/AA tags;
this is automated fixture coverage, not a complete manual accessibility certification.
Independent review: no blocking regressions. Added chronological active-interval
test and assertClean after retry; finance-overview retry-specific unit tests deferred.
Fonts ~756KB TTF with local licenses; WOFF2 optimization deferred, no external CDN.
