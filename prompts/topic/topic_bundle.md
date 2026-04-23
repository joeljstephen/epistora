Generate a grounded topic learning packet from the user's saved corpus.

Topic bundle request:

- Topic / query: {topic}
- Bundle status: {bundle_status}
- Included source count: {source_count}
- Included ready-brief count: {ready_source_count}
- Filters: {filters}

Rules:

1. Use only the included source set provided below.
2. Treat this as a learning packet, not a generic answer or a durable wiki page.
3. If the bundle status is `limited`, say so clearly and avoid over-synthesis.
4. Explain what each source contributes. Do not collapse everything into one bland narrative.
5. Surface disagreements, scope differences, and gaps explicitly.
6. Keep recommendations practical and attention-aware.
7. Stay grounded in compiled source notes. Do not ask to reread raw transcripts or raw evidence
   unless the included source summaries indicate a real limit.
8. Prefer concise, high-signal prose and bullets over filler.

Return markdown with these sections exactly:

## Topic Overview
## Why This Matters
## Best Sources To Start With
## What Each Source Contributed
## Agreements and Disagreements
## Key Concepts / Terms
## Recommended Order
## If I Only Have 10 Minutes
## Gaps / Missing Coverage
## Included Sources

Included source set:

{source_context}
