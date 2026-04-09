Review the following vault summary with the mindset of maintaining a coherent long-lived wiki.

{vault_summary}

Identify:
1. Near-duplicate notes or pages that fragment the same concept
2. Contradictions or unresolved tensions between notes
3. Frequently referenced concepts/entities/topics that still lack strong dedicated pages
4. Merge candidates where navigation would improve if pages were consolidated
5. Navigation gaps where indexes, backlinks, or source-to-topic bridges seem weak
6. Pages that look structurally present but semantically thin
7. Places where raw evidence exists but the compiled layer is still underdeveloped

Respond in JSON format (no markdown fences):
{{
  "duplicate_candidates": [
    {{"notes": ["note1", "note2"], "reason": "why they might be duplicates"}}
  ],
  "potential_contradictions": [
    {{"notes": ["note1", "note2"], "claim1": "...", "claim2": "...", "tension": "..."}}
  ],
  "missing_pages": [
    {{"name": "entity or concept name", "mention_count": 3, "type": "entity|concept|topic"}}
  ],
  "merge_candidates": [
    {{"notes": ["note1", "note2"], "reason": "why they could be merged"}}
  ],
  "navigation_gaps": [
    {{"notes": ["note1", "note2"], "reason": "why navigation or linking is weak"}}
  ],
  "thin_pages": [
    {{"notes": ["note1"], "reason": "why the page looks too shallow to be useful yet"}}
  ]
}}
