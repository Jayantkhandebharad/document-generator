"""
Deterministic pre-parsing: split raw legal text into high-level zones (no LLM).
Uses regex for WHEREFORE, DATED:, ATTORNEY'S VERIFICATION, and pattern match for dashed lines.
"""

import re


def _is_dashed_line(line: str) -> bool:
    """True if line is a dashed/underscore/equals separator (e.g. --------X, ______, or ===)."""
    t = (line or "").strip()
    if not t or len(t) < 3:
        return False
    # Allow trailing X; rest dashes, underscores, equals, spaces
    core = t.rstrip("Xx").rstrip()
    if not core:
        return True
    return all(c in "-_=\t " for c in core) and len(core) >= 3


def _starts_wherefore(line: str) -> bool:
    return bool(re.search(r"^\s*WHEREFORE\b", (line or "").strip(), re.I))


def _starts_dated(line: str) -> bool:
    return bool(re.search(r"\bDATED\s*:", (line or "").strip(), re.I))


def _is_attorney_verification_heading(line: str) -> bool:
    return bool(re.search(r"ATTORNEY'S VERIFICATION", (line or "").strip(), re.I))


def _is_body_start(line: str) -> bool:
    """True if this line starts the summons/notice body (after caption)."""
    t = (line or "").strip()
    if re.search(r"TO THE ABOVE\s*(NAMED\s*)?DEFENDANT\s*:", t, re.I):
        return True
    if re.search(r"You are hereby summoned", t, re.I):
        return True
    return False


def _is_footer_start(line: str) -> bool:
    """True if this line starts a footer section (NOTICE OF ENTRY, certification, etc.)."""
    t = (line or "").strip().upper()
    if "NOTICE OF ENTRY" in t or "NOTICE OF SETTLEMENT" in t:
        return True
    if "PLEASE TAKE NOTICE" in t and "NOTICE OF" in t:
        return True
    if "22 NYCRR 130-1.1" in t or "CERTIFY" in t or "CERTIFICATION" in t:
        return True
    if "Service of a copy" in t and ("admitted" in t.lower() or "hereby" in t.lower()):
        return True
    return False


def parse_zones(text: str) -> dict[str, str]:
    """
    Split raw text into high-level zones (100% deterministic, no LLM).
    Returns dict with keys: caption, body, wherefore, signature, verification, footer.
    Values are the extracted text for each zone (may be empty string).
    """
    zones = {
        "caption": [],
        "body": [],
        "wherefore": [],
        "signature": [],
        "verification": [],
        "footer": [],
    }
    lines = (text or "").split("\n")
    current = "caption"

    for line in lines:
        # State transitions (order matters); transition first so this line goes to the new zone
        if _is_footer_start(line):
            current = "footer"
        elif _is_attorney_verification_heading(line):
            current = "verification"
        elif _starts_dated(line):
            current = "signature"
        elif _starts_wherefore(line):
            current = "wherefore"
        elif _is_body_start(line):
            current = "body"

        zones[current].append(line if line else "")

    return {
        k: "\n".join(v).strip()
        for k, v in zones.items()
    }


def extract_caption_block(text: str) -> str:
    """Return caption zone only (court, county, parties, index, divider)."""
    return parse_zones(text or "").get("caption", "")


def extract_body_until_wherefore(text: str) -> str:
    """Return body zone (main content before WHEREFORE)."""
    return parse_zones(text or "").get("body", "")


def extract_wherefore(text: str) -> str:
    """Return wherefore zone."""
    return parse_zones(text or "").get("wherefore", "")


def extract_signature(text: str) -> str:
    """Return signature zone (DATED: ... signature block)."""
    return parse_zones(text or "").get("signature", "")


def extract_verification(text: str) -> str:
    """Return verification zone (ATTORNEY'S VERIFICATION ...)."""
    return parse_zones(text or "").get("verification", "")


def extract_footer_caption(text: str) -> str:
    """Return footer zone (NOTICE OF ENTRY, certification, etc.)."""
    return parse_zones(text or "").get("footer", "")


# ---------------------------------------------------------------------------
# Region extraction: fixed order for layout. Splits body into summons_intro vs body.
# ---------------------------------------------------------------------------

# Start of allegations / first cause of action (summons_intro ends, body begins)
_CAUSE_OF_ACTION_PATTERN = re.compile(
    r"^\s*AS\s+AND\s+FOR\s+(?:A\s+)?(?:FIRST|SECOND|THIRD|\d+)(?:\s+CAUSE\s+OF\s+ACTION)?\s*[:\s]",
    re.I,
)


def parse_regions(text: str) -> dict[str, str]:
    """
    Split raw text into layout regions (deterministic). Used by region-aware renderer.
    Returns: caption, summons_intro, body, wherefore, signature, verification, footer.
    summons_intro = from "TO THE ABOVE NAMED DEFENDANT" up to (not including) first "AS AND FOR A FIRST CAUSE OF ACTION".
    body = from first cause of action through end of body zone (before WHEREFORE).
    """
    zones = parse_zones(text or "")
    caption = zones.get("caption", "")
    body_raw = zones.get("body", "")
    wherefore = zones.get("wherefore", "")
    signature = zones.get("signature", "")
    verification = zones.get("verification", "")
    footer = zones.get("footer", "")

    summons_intro_lines: list[str] = []
    body_lines: list[str] = []
    body_line_list = (body_raw or "").split("\n") if body_raw else []
    found_cause = False
    for line in body_line_list:
        if not found_cause and _CAUSE_OF_ACTION_PATTERN.search((line or "").strip()):
            found_cause = True
            body_lines.append(line)
            continue
        if not found_cause:
            summons_intro_lines.append(line)
        else:
            body_lines.append(line)

    summons_intro = "\n".join(summons_intro_lines).strip()
    body = "\n".join(body_lines).strip()

    return {
        "caption": caption,
        "summons_intro": summons_intro,
        "body": body,
        "wherefore": wherefore,
        "signature": signature,
        "verification": verification,
        "footer": footer,
    }


# ---------------------------------------------------------------------------
# Caption cleaner: strip embedded caption-like lines/blocks from region text so we do
# not render them as paragraphs. Layout is position-based only (caption_instances);
# never infer caption from content. Use on summons_intro, body, wherefore, signature,
# verification, footer before rendering.
# ---------------------------------------------------------------------------

def _normalize_line_for_caption_match(line: str) -> str:
    """Collapse whitespace so 'SUPERIOR  COURT' and 'NEW  HAVEN  COUNTY' still match."""
    if not line:
        return ""
    return " ".join((line or "").strip().split())


def strip_embedded_caption_blocks(text: str) -> str:
    """
    Remove entire caption blocks (multi-line) from text. Layout is not inferred from content.
    Removes any block that looks like COURT/COUNTY ... through ... SUMMONS AND VERIFIED COMPLAINT
    or similar, so caption text is never re-rendered as paragraphs.
    """
    if not (text or "").strip():
        return text or ""
    s = text
    # Block: from COURT/COUNTY through COMPLAINT or Index No. Bounded to avoid catastrophic backtracking on long text.
    end_marker = r"(?:SUMMONS AND VERIFIED\s+COMPLAINT|Index No\.\s*:[^\n]*)"
    # At most 200 lines between start and end so regex cannot hang on huge input
    line_loop = r"(?:\n[^\n]*){0,200}?"
    for pattern in (
        r"(?ms)\b(SUPERIOR COURT|SUPREME COURT)\b[^\n]*" + line_loop + end_marker,
        r"(?ms)\bNEW HAVEN COUNTY\b[^\n]*" + line_loop + end_marker,
        r"(?m)^[-=]{10,}\s*X?\s*$",  # dash/equals line with optional X
    ):
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    # Collapse multiple blank lines left after removal
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _is_caption_structure_line(line: str) -> bool:
    """True if this line is caption layout (court, county, index, title, divider, party block)."""
    t = _normalize_line_for_caption_match(line or "")
    if not t:
        return False
    if _is_dashed_line(t):
        return True
    u = t.upper()
    # Court header (short line with COURT)
    if "COURT" in u and len(t) < 100:
        if "SUPERIOR COURT" in u or "SUPREME COURT" in u or "COUNTY OF" in u:
            return True
        if u.strip().endswith("COUNTY") or (u.startswith("NEW ") and "COUNTY" in u):
            return True
    # Index No. line
    if re.search(r"INDEX\s+NO\.?\s*:?", u) and len(t) < 100:
        return True
    # SUMMONS AND VERIFIED COMPLAINT title
    if "SUMMONS AND VERIFIED" in u and ("COMPLAINT" in u or len(t) < 50):
        return True
    # Date Filed
    if re.search(r"DATE\s+FILED\s*:?", u) and len(t) < 80:
        return True
    # -against- only
    if re.match(r"^\s*\-against\-\s*$", t, re.I):
        return True
    # Plaintiff/Defendant caption line only: short, ends with ", Plaintiff," or ", Defendant." (not narrative)
    if len(t) < 90 and not re.match(r"^\s*(That|The|Plaintiff|Defendant)\s+", t, re.I):
        if re.search(r",\s*Plaintiff\s*,?\s*$", t, re.I) or re.search(r",\s*Defendant\s*\.?\s*$", t, re.I):
            return True
        if re.match(r"^\s*Plaintiff\s*,?\s*$", t, re.I) or re.match(r"^\s*Defendant\s*\.?\s*$", t, re.I):
            return True
    # Standalone caption-style name line (duplicate block on last pages): e.g. "KELLEY SKAARVA," or "HENRY SARBIESKI," without Plaintiff/Defendant
    if len(t) < 32 and t.endswith(",") and u.isupper() and "COURT" not in u and "COUNTY" not in u and "ESQ" not in u and "ATTORNEY" not in u:
        return True
    return False


def strip_embedded_caption_text(text: str) -> str:
    """
    Remove caption-structure blocks and lines from region text. Caption is layout-only
    (rendered from caption_instances at fixed positions); never re-render caption content
    that appears in the draft. Phase 1: remove entire caption blocks (multi-line regex).
    Phase 2: strip any remaining caption-structure lines line-by-line.
    """
    if not (text or "").strip():
        return text or ""
    # Phase 1: remove entire caption blocks so no reinjection from content
    s = strip_embedded_caption_blocks(text)
    if not s.strip():
        return ""
    # Phase 2: strip any remaining caption lines (e.g. out-of-order or single lines)
    kept = []
    for line in s.split("\n"):
        if not _is_caption_structure_line(line):
            kept.append(line)
    return "\n".join(kept).strip()


# ---------------------------------------------------------------------------
# Structured caption extraction (deterministic, no LLM). Atomic block between dashed lines.
# ---------------------------------------------------------------------------

def _caption_has_court(line: str) -> bool:
    return bool(line and "COURT" in (line or "").upper() and len((line or "").strip()) < 120)


def parse_caption_structured(caption_text: str) -> dict | None:
    """
    Parse caption block into structured fields. Capture plaintiff/defendant as combined unit:
    "KELLEY SKAARVA,\nPlaintiff," -> plaintiff = "KELLEY SKAARVA, Plaintiff,".
    Do not split on dashed line prematurely — treat caption as one atomic block.
    Returns dict: court, county, plaintiff, defendant, index_no, date_filed, divider_line.
    """
    if not (caption_text or "").strip():
        return None
    # Keep all non-empty lines; we'll use first dashed line as divider_line, rest as content
    lines = []
    for ln in (caption_text or "").split("\n"):
        s = ln.strip() if ln else ""
        if s:
            lines.append(s)
    if not lines:
        return None

    court = ""
    county = ""
    plaintiff = ""
    defendant = ""
    index_no = ""
    date_filed = ""
    divider_line = ""

    i = 0
    # Optional leading dashed line (opening divider)
    if i < len(lines) and _is_dashed_line(lines[i]):
        divider_line = lines[i]
        i += 1

    # Court (first line with COURT)
    while i < len(lines):
        if _caption_has_court(lines[i]):
            court = lines[i]
            i += 1
            break
        if _is_dashed_line(lines[i]):
            if not divider_line:
                divider_line = lines[i]
            i += 1
            continue
        i += 1

    # County
    while i < len(lines):
        t = lines[i].upper()
        if "COUNTY" in t and len(lines[i]) < 80:
            county = lines[i]
            i += 1
            break
        if _is_dashed_line(lines[i]):
            if not divider_line:
                divider_line = lines[i]
            i += 1
            continue
        i += 1

    # First divider after court/county (do not stop parsing; keep going for date/index/parties)
    if i < len(lines) and _is_dashed_line(lines[i]):
        if not divider_line:
            divider_line = lines[i]
        i += 1

    # Rest: date, index, plaintiff, -against-, defendant. Combine "NAME,\nPlaintiff," into one.
    while i < len(lines):
        line = lines[i]
        t = line.upper()
        if _is_dashed_line(line):
            if not divider_line:
                divider_line = line
            i += 1
            continue
        if re.search(r"DATE\s+FILED\s*:\s*", t):
            m = re.search(r"DATE\s+FILED\s*:\s*(.+)", line, re.I)
            date_filed = (m.group(1).strip() if m else "").strip()
            i += 1
            continue
        if re.search(r"INDEX\s+NO\.?\s*:?\s*", t):
            m = re.search(r"INDEX\s+NO\.?\s*:?\s*(.+)", line, re.I)
            index_no = (m.group(1).strip() if m else "").strip()
            i += 1
            continue
        if re.search(r"^\s*\-against\-", line, re.I):
            i += 1
            continue
        # Plaintiff: combine with previous line if it's a name (e.g. "KELLEY SKAARVA," then "Plaintiff,")
        if "PLAINTIFF" in t and ("," in line or "." in line) and len(line) < 120:
            if not plaintiff and i > 0:
                prev = lines[i - 1].strip()
                if prev and prev.endswith(",") and not any(x in prev.upper() for x in ("COURT", "COUNTY", "INDEX", "DATE", "PLAINTIFF", "DEFENDANT")):
                    plaintiff = prev + " " + line
                else:
                    plaintiff = line
            else:
                plaintiff = plaintiff or line
            i += 1
            continue
        # Defendant: combine with previous line if it's a name (e.g. "HENRY SARBIESKI," then "Defendant.")
        if "DEFENDANT" in t and ("." in line or "," in line) and len(line) < 120:
            if not defendant and i > 0:
                prev = lines[i - 1].strip()
                if prev and (prev.endswith(",") or prev.endswith(".")) and not any(x in prev.upper() for x in ("COURT", "COUNTY", "INDEX", "DATE", "PLAINTIFF", "DEFENDANT")):
                    defendant = prev + " " + line
                else:
                    defendant = line
            else:
                defendant = defendant or line
            i += 1
            continue
        # Combined line e.g. "KELLEY SKAARVA,     Index No.: NNHCV216111723S"
        if "INDEX NO" in t and not index_no:
            m = re.search(r"INDEX\s+NO\.?\s*:?\s*([^\s,]+(?:\s+[^\s,]+)*)", line, re.I)
            if m:
                index_no = m.group(1).strip()
            parts = re.split(r"\t|,\s*Index\s+No\.?", line, 1, re.I)
            if parts and parts[0].strip() and not plaintiff:
                plaintiff = parts[0].strip() + ("," if not parts[0].rstrip().endswith(",") else "")
        i += 1

    return {
        "court": court,
        "county": county,
        "plaintiff": plaintiff,
        "defendant": defendant,
        "index_no": index_no,
        "date_filed": date_filed or "[Date]",
        "divider_line": divider_line or "----------------------------------------------------------------------X",
    }


# ---------------------------------------------------------------------------
# All caption instances: summons_caption, complaint_caption, footer_caption.
# ---------------------------------------------------------------------------

def _is_caption_block_start(line: str, after_content: bool) -> bool:
    """True if this line can start a caption block (court or opening divider)."""
    t = (line or "").strip()
    if not t:
        return False
    if _caption_has_court(t):
        return True
    if _is_dashed_line(t) and len(t) >= 10:
        return True
    return False


def _find_caption_block_ranges(text: str) -> list[tuple[int, int, str]]:
    """
    Find all caption blocks in text. Each block is (start_line_idx, end_line_idx, block_text).
    A block starts at COURT or dashed line; ends at closing dashed line or body start.
    """
    lines = (text or "").split("\n")
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = (line or "").strip()
        if not _is_caption_block_start(stripped, after_content=(i > 0 and any(lines[i-1].strip()))):
            i += 1
            continue
        start = i
        # If we started on a dashed line, next should be court or we skip
        if _is_dashed_line(stripped) and not _caption_has_court(stripped):
            i += 1
            if i < len(lines) and _caption_has_court(lines[i].strip()):
                start = i
            else:
                continue
        collected = []
        seen_dashed = 0
        while i < len(lines):
            ln = lines[i]
            s = (ln or "").strip()
            if _is_body_start(ln) or _CAUSE_OF_ACTION_PATTERN.search(s):
                break
            if _is_footer_start(ln):
                break
            if _starts_wherefore(ln):
                break
            if _is_dashed_line(s):
                seen_dashed += 1
                collected.append(ln)
                i += 1
                # Closing divider: end block after this line
                if seen_dashed >= 1 and len(collected) > 3:
                    break
                continue
            if s:
                collected.append(ln)
            i += 1
        block_text = "\n".join(collected).strip()
        if block_text and (_caption_has_court(block_text.split("\n")[0].strip()) or any(_caption_has_court(l.strip()) for l in block_text.split("\n"))):
            blocks.append((start, i - 1, block_text))
    return blocks


def extract_all_captions(text: str) -> list[dict]:
    """
    Detect all caption instances and classify: summons_caption, complaint_caption, footer_caption.
    Returns list of {"type": "summons_caption"|"complaint_caption"|"footer_caption", "text": str, "structured": dict}.
    Positions: page top = summons_caption; before "AS AND FOR A FIRST CAUSE" = complaint_caption; in footer = footer_caption.
    """
    if not (text or "").strip():
        return []
    ranges = _find_caption_block_ranges(text)
    lines = text.split("\n")
    # Line indices of section boundaries
    cause_line_idx = next((i for i, ln in enumerate(lines) if _CAUSE_OF_ACTION_PATTERN.search((ln or "").strip())), len(lines))
    footer_start_idx = next((i for i, ln in enumerate(lines) if _is_footer_start(ln)), len(lines))

    caption_instances = []
    for idx, (start, end, block_text) in enumerate(ranges):
        structured = parse_caption_structured(block_text)
        if not structured:
            continue
        # Classify by position: first block before cause = summons; block after cause but before footer = complaint; block in footer = footer
        if start < cause_line_idx and idx == 0:
            caption_type = "summons_caption"
        elif start >= footer_start_idx or (start > len(lines) * 0.6):
            caption_type = "footer_caption"
        elif start >= cause_line_idx or idx >= 1:
            caption_type = "complaint_caption"
        else:
            caption_type = "summons_caption"

        caption_instances.append({
            "type": caption_type,
            "text": block_text,
            "structured": structured,
        })

    # Return in fixed order: summons_caption, complaint_caption, footer_caption (first of each)
    order_wanted = ("summons_caption", "complaint_caption", "footer_caption")
    by_type = {t: None for t in order_wanted}
    for inst in caption_instances:
        t = inst["type"]
        if t in by_type and by_type[t] is None:
            by_type[t] = inst
    return [by_type[t] for t in order_wanted if by_type[t] is not None]
