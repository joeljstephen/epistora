# JSON Export Sink

This document describes the built-in `JsonExportSink`, which publishes
canonical artifact bundles without relying on markdown-vault rendering.

## Why It Exists

The current architecture requires the canonical artifact layer and sink
abstraction to be real, not just a wrapper around markdown writing.

`JsonExportSink` proves that by consuming the same `ArtifactBundle` boundary used by the markdown sink and emitting a machine-facing export with no compiler special cases.

## Default Behavior

The markdown vault remains the default sink.

JSON export is opt-in through configuration:

```bash
ARTIFACT_SINK_IDS=markdown_vault,json_export
```

If you want JSON export only:

```bash
ARTIFACT_SINK_IDS=json_export
```

The default export location is:

```text
<vault>/.system/exports/json/<source_type>/<slug>.json
```

You can override that with:

```bash
JSON_EXPORT_DIR=.system/exports/custom-json
```

## Export Schema

Each exported file contains one canonical bundle for one source slug.

Top-level schema:

- `schema_version`
- `export`
- `artifact_counts`
- `bundle`

`export` fields:

- `sink_id`
- `source_artifact_id`
- `source_slug`
- `source_type`

`artifact_counts` fields:

- `topics`
- `entities`
- `concepts`
- `relationships`
- `synthesis`
- `evidence_references`

`bundle` fields:

- `source`
- `topics`
- `entities`
- `concepts`
- `relationships`
- `synthesis`
- `evidence_references`

The `bundle` payload is the canonical artifact layer serialized to JSON. That means downstream tooling can consume:

- source summaries and metadata
- topic/entity/concept artifacts
- relationship edges
- evidence references

without parsing markdown notes.

## Determinism

The JSON export is designed to be deterministic:

- output path is derived from canonical source type and slug
- collections are sorted by artifact id before serialization
- object keys are serialized in sorted order
- no timestamps are injected into the export payload

That makes the sink easy to diff and test.

## Example

```json
{
  "artifact_counts": {
    "concepts": 1,
    "entities": 1,
    "evidence_references": 1,
    "relationships": 6,
    "synthesis": 0,
    "topics": 1
  },
  "bundle": {
    "concepts": [
      {
        "definition": "Persistent state across tasks",
        "id": "concept:durable-memory",
        "slug": "durable-memory",
        "title": "Durable memory"
      }
    ],
    "source": {
      "id": "source:agent-memory-systems",
      "slug": "agent-memory-systems",
      "source_type": "article",
      "title": "Agent Memory Systems"
    },
    "topics": [
      {
        "id": "topic:agent-memory",
        "slug": "agent-memory",
        "title": "Agent Memory"
      }
    ]
  },
  "export": {
    "sink_id": "json_export",
    "source_artifact_id": "source:agent-memory-systems",
    "source_slug": "agent-memory-systems",
    "source_type": "article"
  },
  "schema_version": "epistora.json_export.v1"
}
```

The real export includes the full canonical bundle, including relationship and evidence-reference collections.

## Relationship To MarkdownVaultSink

`JsonExportSink` does not replace `MarkdownVaultSink`.

The intended proof is coexistence:

- `markdown_vault` remains the primary default sink
- `json_export` can be enabled alongside it
- both consume the same canonical artifact bundle through the sink boundary

That is the architectural proof that the compiler is publishing artifacts, not markdown-specific objects.
