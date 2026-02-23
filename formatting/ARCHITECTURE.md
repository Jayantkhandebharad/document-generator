# Formatter architecture

## Pipeline (region-aware layout)

**Layout dictates where content goes.** No slot-fill for structure.

1. **Region extraction** (`utils/zone_parser.py`): `parse_regions()` splits raw text into: caption, summons_intro, body, wherefore, signature, verification, footer. Body is split at first "AS AND FOR A FIRST CAUSE OF ACTION". No LLM.

2. **Caption** (`parse_caption_structured()`): Deterministic parse → court, county, plaintiff, defendant, index_no, date_filed, divider_line. Rendered as table only.

3. **Caption cleaner** (`utils/zone_parser.py` — `strip_embedded_caption_text()`): Before rendering region paragraphs, strip caption-structure lines (court, county, index no., divider, plaintiff/defendant block) from each region’s text so the draft’s repeated caption blocks are not rendered as body. Only the structured caption tables (summons/complaint/footer) are output.

4. **Render by region** (`utils/formatter.py` — `render_document_by_region()`): Fixed order — (1) caption table, (2) summons_intro, (3) body, (4) wherefore, (5) signature, (6) verification, (7) footer. **Divider only in caption (table) and footer;** never in body/wherefore/signature/verification. Signature and verification are atomic (one paragraph per line).

5. **Style injector**: Blueprint `paragraph_format` and `run_format` from template styles per region.

---

## Implemented

### Upgrade 1 - Style-only injection (critical)
- **No manual formatting.** When `template_structure` is present we assign `paragraph.style = template_style` and add text only. No `_apply_paragraph_format()` or `_apply_run_format()`.
- **Clone styles utility:** `clone_styles(src_doc, dst_doc)` in `utils/style_extractor.py` copies paragraph style definitions from template to a destination doc (for building new docs from scratch).
- Word handles indentation, numbering, spacing from the template’s style definitions.

### Upgrade 2 - No fake numbering
- **Removed** prepending `"1. ", "2. "` in code. List/numbered paragraphs get the template’s list style; numbering comes from the style (and, when implemented, from cloned numbering definitions).
- Leading "1. " etc. from LLM output is stripped so the paragraph contains only the allegation text.

### Upgrade 3 - Section replication
- **Template section preserved.** We no longer override section margins after `clear_document_body(doc)`. Page breaks, margins, and columns come from the template.

### Upgrade 4 - Preserve blank paragraphs
- **No aggressive trim when using template.** `remove_trailing_empty_and_noise(doc)` is skipped when slot-fill was used (`template_structure` is not None) so legal spacing and blank paragraphs are preserved.

### Upgrade 5 - Region-aware layout (Stage 3)
- **Slot-fill only.** Template structure slots → fill text → preserve structure. LLM fills slots; renderer only injects text into the template’s styles and Caption = table only. Divider only in caption and footer; no divider in body/wherefore/signature/verification.

---

## TODO (future)

### Real numbering cloning (Upgrade 2 full)
- Copy **abstract numbering definitions** from template XML: `doc.part.numbering_part` (and related parts).
- Attach numbering to paragraphs so allegations align exactly with the template.
- Until then, numbering is driven by the template’s list styles in the same document (we edit the template in place).

### Section replication when building a new doc
- If building from a **new** document, clone **section properties XML** (`sectPr`).

---

## File roles

| File | Role |
|------|------|
| `utils/style_extractor.py` | Extract styles, template structure, line samples; `clone_styles()` |
| `utils/formatter.py` | `render_document_by_region()`, `_render_region_paragraphs()`, `_render_caption_table()`; `clear_document_body()` |
| `utils/zone_parser.py` | `parse_regions()`, `parse_caption_structured()`, `strip_embedded_caption_text()`: region + caption extraction; caption deduplication |
| `backend.py` | Load template → extract styles → parse_regions → render_document_by_region (no LLM for layout) |
