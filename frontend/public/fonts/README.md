# Local UI typefaces

Downloaded 2026-10-23 from google/fonts (main). Served locally; no runtime font CDN
or third-party request. Both typefaces use SIL Open Font License 1.1; original
license/copyright files are adjacent. font-display: swap preserves fallback text.

- Barlow Semi Condensed SemiBold (headings):
  https://github.com/google/fonts/blob/main/ofl/barlowsemicondensed/BarlowSemiCondensed-SemiBold.ttf
  SHA256 bd299f4bc5b44d30be8d42e9bad3a5df7d66af1cd55d0ed72a8b8916360a1424
- Source Sans 3 variable (body, weights 200–900):
  https://github.com/google/fonts/blob/main/ofl/sourcesans3/SourceSans3%5Bwght%5D.ttf
  SHA256 042fe2cc0b933e328410d7acbd0aa6a1873dca5aef81875f4bc214b08825c7b9

Files are vendored bytes rather than fetched at build time. Combined font payload
is about 756 KB uncompressed. Future WOFF2 conversion/subsetting is a separate
optimization and must retain Polish glyphs and the licenses.
