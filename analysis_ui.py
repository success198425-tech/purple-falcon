"""Gradio analysis tab for Purple Falcon.

This module is used by purple_falcon_app.py to add file analysis and report
exports to the existing Falcon UI without duplicating the chat application.
"""
from __future__ import annotations

import shutil
import tempfile
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr

from data_analyzer import analyze_table, analyze_text, export_reports, read_file

ANALYSIS_TYPES = [
    ".csv", ".tsv", ".json", ".xlsx", ".xls", ".txt", ".md", ".log",
    ".pdf", ".docx", ".pptx",
]


def _path(upload):
    if upload is None:
        return None
    if isinstance(upload, str):
        return Path(upload)
    if isinstance(upload, dict):
        return Path(upload.get("path") or upload.get("name"))
    return Path(getattr(upload, "path", None) or getattr(upload, "name", None))


def _analyze_uploads(uploads, group_by, value, top, formats):
    paths = [_path(item) for item in (uploads or [])]
    paths = [p for p in paths if p and p.exists()]
    if not paths:
        return "Please upload at least one supported file.", [], None

    try:
        import pandas as pd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Analysis dependencies are missing. Run: pip install -r requirements-analysis.txt", [], None

    out = Path(tempfile.mkdtemp(prefix="purple_falcon_analysis_"))
    raw = out / "raw_files"
    raw.mkdir()
    # export_reports expects generated_at because it writes it into DOCX metadata.
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
        "executive_summary": "",
    }
    frames = []
    args = Namespace(group_by=(group_by or None), value=(value or None), top=int(top or 10))

    for path in paths:
        shutil.copy2(path, raw / path.name)
        data, kind = read_file(path, pd)
        if kind == "table" and data is not None:
            result = analyze_table(data, path.name, args, out, plt)
            frames.append((path.name, data))
        elif kind == "text" and data is not None:
            result = analyze_text(data, path.name)
        else:
            result = {"file": path.name, "status": "could not analyze"}
        report["files"].append(result)

    tables = [item for item in report["files"] if "rows" in item]
    rows = sum(item.get("rows", 0) for item in tables)
    report["executive_summary"] = (
        f"Analyzed {len(report['files'])} file(s), including {len(tables)} structured dataset(s), "
        f"with {rows:,} total row(s). Review missing values, duplicates, outliers, and source context "
        "before making decisions."
    )
    export_reports(report, frames, out, set(formats or []), raw)

    files = [str(p) for p in sorted(out.rglob("*")) if p.is_file()]
    charts = [p for p in files if p.lower().endswith(".png")]
    rendered = "## Analysis complete\n\n" + report["executive_summary"]
    rendered += "\n\n### Recommendations\n"
    for item in report["files"]:
        for recommendation in item.get("recommendations", []):
            rendered += f"- {recommendation}\n"
    return rendered, charts, str(out / "purple_falcon_analysis.zip")


def add_analysis_tab(demo, css_class=None):
    """Add the analysis interface to an existing Gradio Blocks application."""
    with demo:
        with gr.Tab("📊 Data Analysis & Reports"):
            gr.Markdown(
                "### Analyze attachments and export reports\n"
                "Upload CSV, Excel, JSON, PDF, Word, PowerPoint, or text files. "
                "The original files remain in the downloadable ZIP bundle."
            )
            uploads = gr.File(
                label="Attachments",
                file_count="multiple",
                file_types=ANALYSIS_TYPES,
                type="filepath",
            )
            with gr.Row():
                group_by = gr.Textbox(label="Group-by column (optional)", placeholder="Region")
                value = gr.Textbox(label="Numeric value column (optional)", placeholder="Sales")
                top = gr.Number(label="Top groups", value=10, precision=0)
            formats = gr.CheckboxGroup(
                ["xlsx", "docx", "pptx"],
                value=["xlsx", "docx", "pptx"],
                label="Export formats",
            )
            run = gr.Button("🚀 Analyze and create reports", variant="primary")
            status = gr.Markdown()
            charts = gr.Gallery(label="Generated charts", columns=2, height="auto")
            download = gr.File(label="Download complete raw/report ZIP", interactive=False)
            run.click(
                _analyze_uploads,
                inputs=[uploads, group_by, value, top, formats],
                outputs=[status, charts, download],
                show_progress="full",
            )
    return demo
