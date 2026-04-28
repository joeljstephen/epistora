# Storage Tiers

This document describes Epistora's storage-tier foundation for large raw
evidence.

## Why This Exists

The architecture calls for a local-first evidence retention policy with
practical tiers:

- hot
- warm
- cold/blob

Epistora already preserved raw evidence strongly, but it kept the hottest visible `raw/` layer responsible for the full payload every time. That works for small captures, but large transcripts, extracted PDF text, and readable article archives can bloat the working vault unnecessarily.

The current storage policy keeps evidence auditable while separating the visible
manifest layer from heavy payload storage.

## Tier Model

Epistora now treats evidence storage like this:

- hot: compiled source notes in `wiki/sources/`
- warm: stable immutable raw notes in `raw/`
- cold: oversized payloads in `.system/blobs/`

The important rule is that `raw/` does not disappear. It remains the stable human-facing and agent-facing evidence entrypoint.

## Blob-Backed Raw Evidence

When a raw capture exceeds the configured threshold:

1. Epistora writes the full payload into `.system/blobs/<kind>/<slug>/primary.<ext>`
2. Epistora writes a warm raw note in `raw/` as an immutable manifest-plus-preview
3. The source note still points at the raw note
4. The raw note points at the blob payload and records audit metadata

That means the reference chain stays inspectable:

```text
wiki/sources/.../source.md
  -> raw/.../capture.md
    -> .system/blobs/.../primary.md|txt|html
```

## What Gets Stored In The Blob Tier

Epistora stores a full preserved payload in `.system/blobs/` when it is large enough, such as:

- long markdown article archives
- long YouTube transcript archives
- large plain-text captures
- HTML captures when HTML is the preserved payload

The blob file format is chosen from the preserved evidence payload:

- `.md` for archived markdown
- `.html` for preserved HTML payloads
- `.txt` for plain text

## Raw Note Metadata

Blob-backed raw notes include inspectable metadata such as:

- `storage_tier`
- `blob_path`
- `blob_storage_tier`
- `blob_bytes`
- `blob_sha256`
- `blob_media_type`

The raw note body also keeps:

- a readable preview
- a stable link to the full blob payload
- explicit storage notes explaining that the visible note is the manifest layer

## Source Note Metadata

Source notes remain readable and continue to point at `raw_capture_path`.

When the raw evidence is blob-backed, source notes also record:

- `raw_storage_tier`
- `raw_blob_path`
- `raw_blob_storage_tier`
- `raw_blob_bytes`
- `raw_blob_sha256`

This keeps evidence provenance visible without forcing users or agents to parse `.system/` blindly.

## Configuration

Relevant settings:

- `EVIDENCE_BLOB_DIR`
- `EVIDENCE_BLOB_THRESHOLD_BYTES`
- `EVIDENCE_BLOB_PREVIEW_CHARS`

Defaults:

- blob dir: `.system/blobs`
- blob threshold: `50000` bytes
- raw-note preview: `4000` chars

## Backward Compatibility

The storage-tier behavior is additive and migration-safe:

- existing vaults continue to work
- existing `raw_capture_path` references remain valid
- old raw notes are not silently upgraded or relocated
- reingest preserves an existing raw note as the stable reference if it already exists

That is intentional. The goal here is to add storage-tier support, not rewrite prior evidence history.

## Auditability

The design keeps evidence trustworthy because:

- visible source notes still point to visible raw notes
- raw notes stay immutable
- blob-backed raw notes expose the blob path and checksum
- heavy evidence is moved out of the hottest working layer without being hidden

The blob tier is therefore storage-efficient, but not opaque.
