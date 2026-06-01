# FileOrganizer Research Report

This is the canonical research summary. Full pre-consolidation source documents
are archived at:

- `docs/archive/research/RESEARCH.md`
- `docs/archive/research/RESEARCH_IDEAS.md`

## Current Findings

- FileOrganizer should continue evolving from a one-shot sorter into a durable
  asset catalog, browser, and safe plan/apply system.
- Every destructive operation should remain plan-first, editable, journaled,
  and reportable.
- Classification quality improves most when metadata, marketplace lookups,
  fingerprints, rules, and AI cooperate with visible confidence/provenance.
- Watch mode should use stable file signatures and pending state rather than
  simple "seen path" tracking.
- Portable metadata matters: catalog export, sidecars, XMP/IPTC where possible,
  and relinking by fingerprint/path hints reduce lock-in.

## Research Tracks

- Plan-first apply pipeline.
- Asset catalog and browser.
- Multimodal classification router.
- Rule chains and watch service.
- Metadata interoperability.
- Dedup and library hygiene.
- Marketplace and source provenance.

## Archive Use

- `RESEARCH.md` preserves external research notes and implementation tracks.
- `RESEARCH_IDEAS.md` preserves deeper proposal notes for metadata extraction,
  marketplace lookup, content-addressed dedup, YAML rules, embeddings, UI
  review, and related follow-up work.
