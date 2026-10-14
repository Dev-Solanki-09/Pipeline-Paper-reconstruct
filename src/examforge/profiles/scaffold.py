"""
Phase 13.4 & 13.5 — Profile Scaffolding & Visual Preview Generator.

Generates draft ExamProfile YAML specifications in profiles/learned/
and visual overlay debugging HTML files for human verification.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import yaml

from examforge.ir.schema import ExamDocument
from examforge.profiles.fingerprint import ProfileCache, extract_document_fingerprint
from examforge.profiles.infer_llm import complete_profile_llm
from examforge.profiles.infer_rules import infer_profile_deterministic
from examforge.profiles.schema import ExamProfile


def _render_preview_html(
    doc: ExamDocument,
    profile: ExamProfile,
    gutters: list[float],
    low_confidence_fields: list[str],
    overall_confidence: float,
) -> str:
    """Generate visual overlay HTML showing detected gutters, questions, and options."""
    low_conf_badges = (
        "".join(
            f'<span class="badge badge-warn">{html.escape(f)}</span> '
            for f in low_confidence_fields
        )
        or '<span class="badge badge-ok">All fields verified</span>'
    )

    pages_html = []
    # Render first 3 pages
    for page in doc.pages[:3]:
        p_w = float(page.width_px or 600.0)
        p_h = float(page.height_px or 800.0)

        # Draw gutters
        gutter_elements = "".join(
            f'<div class="gutter" style="left: {(g / p_w) * 100:.1f}%;"></div>' for g in gutters
        )

        # Draw blocks
        block_elements = []
        p_blocks = [b for b in doc.blocks if b.page == page.page_number]
        for b in p_blocks:
            left = (b.bbox.x1 / p_w) * 100
            top = (b.bbox.y1 / p_h) * 100
            width = ((b.bbox.x2 - b.bbox.x1) / p_w) * 100
            height = ((b.bbox.y2 - b.bbox.y1) / p_h) * 100

            # Tag block kind
            is_q = any(
                pat for pat in profile.numbering.patterns if b.text.strip().startswith(pat[:2])
            )
            is_opt = any(lbl for lbl in profile.options.label_schemes if lbl in b.text)
            cls_name = "block-q" if is_q else ("block-opt" if is_opt else "block-other")

            block_elements.append(
                f'<div class="block {cls_name}" '
                f'style="left:{left:.1f}%; top:{top:.1f}%; width:{width:.1f}%; '
                f'height:{height:.1f}%;" '
                f'title="{html.escape(b.text[:80])}">'
                f'<span class="block-label">{html.escape(b.id)}: {html.escape(b.text[:35])}</span>'
                f"</div>"
            )

        pages_html.append(
            f'<div class="page-container" style="aspect-ratio: {p_w}/{p_h};">'
            f'<div class="page-header">Page {page.page_number} ({int(p_w)}x{int(p_h)})</div>'
            f"{gutter_elements}"
            f"{''.join(block_elements)}"
            f"</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Profile Preview: {html.escape(profile.id)}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 20px; background: #0f172a; color: #f8fafc;
  }}
  .header {{
    background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 24px;
    border: 1px solid #334155;
  }}
  .header h1 {{ margin: 0 0 10px 0; font-size: 20px; color: #38bdf8; }}
  .badge {{
    display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px;
    font-weight: 600; margin-right: 6px;
  }}
  .badge-warn {{ background: #7c2d12; color: #fdba74; }}
  .badge-ok {{ background: #14532d; color: #86efac; }}
  .meta-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px; margin-top: 14px; font-size: 14px;
  }}
  .page-container {{
    position: relative; width: 100%; max-width: 700px; margin: 0 auto 30px auto;
    background: #ffffff; border-radius: 6px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    overflow: hidden;
  }}
  .page-header {{
    position: absolute; top: 8px; right: 8px; font-size: 11px; color: #64748b;
    z-index: 10; font-weight: bold; background: rgba(255,255,255,0.8);
    padding: 2px 6px; border-radius: 4px;
  }}
  .gutter {{
    position: absolute; top: 0; bottom: 0; width: 2px; border-left: 2px dashed #ef4444;
    z-index: 5; pointer-events: none;
  }}
  .block {{
    position: absolute; box-sizing: border-box; border-radius: 3px; font-size: 9px;
    overflow: hidden; padding: 2px; z-index: 2; transition: opacity 0.2s;
  }}
  .block-q {{ border: 1.5px solid #16a34a; background: rgba(22, 163, 74, 0.15); color: #14532d; }}
  .block-opt {{
    border: 1.5px solid #2563eb; background: rgba(37, 99, 235, 0.15); color: #1e3a8a;
  }}
  .block-other {{
    border: 1px solid #cbd5e1; background: rgba(241, 245, 249, 0.4); color: #475569;
  }}
  .block-label {{
    display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-weight: 500;
  }}
</style>
</head>
<body>
  <div class="header">
    <h1>Profile Preview: {html.escape(profile.id)}</h1>
    <div>
      <strong>Overall Confidence:</strong> {overall_confidence:.1%} &nbsp;|&nbsp;
      <strong>Maturity:</strong> {profile.maturity}
    </div>
    <div style="margin-top: 8px;"><strong>Attention Fields:</strong> {low_conf_badges}</div>
    <div class="meta-grid">
      <div>
        <strong>Languages:</strong> {", ".join(lang.code for lang in profile.languages)}
        ({profile.language_layout})
      </div>
      <div><strong>Columns:</strong> {profile.layout.columns}</div>
      <div><strong>Numbering:</strong> {", ".join(profile.numbering.patterns)}</div>
      <div><strong>Option Labels:</strong> {", ".join(profile.options.label_schemes)}</div>
    </div>
  </div>
  {"".join(pages_html)}
</body>
</html>
"""


def scaffold_profile(
    doc: ExamDocument,
    output_dir: Path | str = Path("profiles/learned"),
    profile_id: str | None = None,
    cache_path: Path | str | None = None,
    llm_client: Any | None = None,
) -> tuple[Path, Path, ExamProfile, list[str]]:
    """
    Scaffold a new draft profile from an ExamDocument, emitting YAML and HTML preview.

    Returns:
        tuple: (yaml_path, preview_html_path, ExamProfile, low_confidence_fields)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fingerprint & Deterministic Inference
    fp = extract_document_fingerprint(doc)
    infer_res = infer_profile_deterministic(doc, fp)

    # 2. LLM completion for low-confidence fields if needed
    if infer_res.low_confidence_fields and llm_client:
        profile, _ = complete_profile_llm(infer_res, doc, llm_client)
    else:
        profile = infer_res.profile

    # 3. Override ID if requested
    if profile_id:
        profile = ExamProfile(
            id=profile_id,
            name=f"Scaffolded Profile {profile_id}",
            maturity="experimental",
            languages=profile.languages,
            language_layout=profile.language_layout,
            layout=profile.layout,
            numbering=profile.numbering,
            options=profile.options,
            furniture_branding=profile.furniture_branding,
            expected_kinds=profile.expected_kinds,
            marking=profile.marking,
            answer_key_patterns=profile.answer_key_patterns,
            rules=profile.rules,
            output=profile.output,
        )

    # 4. Save YAML
    yaml_path = output_dir / f"{profile.id}.yaml"
    yaml_dict = profile.model_dump()
    yaml_text = yaml.dump(yaml_dict, sort_keys=False, allow_unicode=True)
    yaml_path.write_text(yaml_text, encoding="utf-8")

    # 5. Save HTML Preview
    html_path = output_dir / "profile_preview.html"
    preview_html = _render_preview_html(
        doc=doc,
        profile=profile,
        gutters=fp.gutters,
        low_confidence_fields=infer_res.low_confidence_fields,
        overall_confidence=infer_res.overall_confidence,
    )
    html_path.write_text(preview_html, encoding="utf-8")

    # 6. Record to ProfileCache
    cache = ProfileCache(cache_path or Path("data/profiles/profile_cache.sqlite"))
    cache.store(
        fingerprint_hash=fp.doc_hash,
        profile_id=profile.id,
        profile_yaml=yaml_text,
        confidence=infer_res.overall_confidence,
    )

    return yaml_path, html_path, profile, infer_res.low_confidence_fields
