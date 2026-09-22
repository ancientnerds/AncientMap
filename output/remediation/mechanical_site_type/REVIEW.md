# site_type values outside the canonical list - for hand review

Built 2026-09-22T22:28:06+00:00 by `scripts/remediation/mechanical/site_type_shape.py`, read live (read-only). The canonical list is `pipeline/normalizers/site_type.py:CANONICAL_TYPES`, which mirrors the category colours of the globe (`ancient-nerds-map/src/constants/colors.ts`). None of these rows is written by the mechanical lane.

| site | value | journal | why not written | the decision it needs |
|---|---|---|---|---|
| Altar of Athena Polias (`78c18ef3-5f91-4629-bfef-37b0f13b2bef`) | `Altar` | phase3:batch-0240:chunk-0001 (P3/site_type): 'Megalithic structures' -> 'Altar' | `outside-canonical-list` | add the word to CANONICAL_TYPES and colors.ts, or map it to a canonical type |
| Boeotian Treasury (`8afd1020-1c36-499b-ae38-8aaa9f9d4170`) | `Treasury` | phase3:batch-0078:chunk-0001 (P3/site_type): 'Megalithic structures' -> 'Treasury' | `outside-canonical-list` | add the word to CANONICAL_TYPES and colors.ts, or map it to a canonical type |
| Cnidian Treasury (`9e827a4b-0855-4414-946b-b5fc3e3efb9b`) | `Treasury` | phase3:batch-0269:chunk-0001 (P3/site_type): 'Megalithic structures' -> 'Treasury' | `outside-canonical-list` | add the word to CANONICAL_TYPES and colors.ts, or map it to a canonical type |
| Siphnian Treasury (`9624278c-1080-4a2a-ae2e-11829bda299a`) | `Treasury` | phase3:batch-0213:chunk-0001 (P3/site_type): 'Megalithic structures' -> 'Treasury' | `outside-canonical-list` | add the word to CANONICAL_TYPES and colors.ts, or map it to a canonical type |
| Mookambika Wildlife Sanctuary Kodachadri (`2133d54c-f352-4325-ae0c-dd532f9a65d3`) | `suspect_modern` | 'suspect_modern' (marker-token) has no journal row: it predates the remediation, so there is no written value to restore - hand review | `no-journal-row` | decide the type by hand (no written value to restore) |
