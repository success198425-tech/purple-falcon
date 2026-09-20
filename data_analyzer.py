"""Purple Falcon file analysis and report generator.

Examples:
    python data_analyzer.py data.csv --out reports/sales
    python data_analyzer.py ./attachments --out reports/run --formats xlsx docx pptx
    python data_analyzer.py data.xlsx --sheet Sales --group-by Region --value Sales

The command creates a report directory containing raw copied inputs, CSV summaries,
PNG charts, Excel/Word/PowerPoint reports, analysis.json, and a ZIP bundle.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED = {".csv", ".tsv", ".json", ".xlsx", ".xls", ".txt", ".md", ".log", ".pdf", ".docx", ".pptx"}


def die(message: str) -> None:
    raise SystemExit(f"Error: {message}")


def imports():
    try:
        import pandas as pd
        import matplotlib.pyplot as plt
    except ImportError:
        die("Install dependencies first: pip install -r requirements-analysis.txt")
    return pd, plt


def files_from(inputs: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            die(f"Input does not exist: {path}")
        if path.is_dir():
            found.extend(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
        elif path.suffix.lower() in SUPPORTED:
            found.append(path)
        else:
            print(f"Skipping unsupported file: {path}", file=sys.stderr)
    unique = list(dict.fromkeys(p.resolve() for p in found))
    if not unique:
        die("No supported files found")
    return unique


def read_file(path: Path, pd):
    ext = path.suffix.lower()
    try:
        if ext in {".csv", ".tsv"}:
            return pd.read_csv(path, sep="\t" if ext == ".tsv" else ","), "table"
        if ext in {".xlsx", ".xls"}:
            sheets = pd.read_excel(path, sheet_name=None)
            frame = next((df for df in sheets.values() if not df.empty), pd.DataFrame())
            return frame, "table"
        if ext == ".json":
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return pd.json_normalize(data), "table"
            if isinstance(data, dict):
                try:
                    return pd.json_normalize(data), "table"
                except Exception:
                    return pd.DataFrame([data]), "table"
        if ext in {".txt", ".md", ".log"}:
            return path.read_text(encoding="utf-8", errors="replace"), "text"
        if ext == ".pdf":
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages), "text"
        if ext == ".docx":
            from docx import Document
            return "\n".join(p.text for p in Document(str(path)).paragraphs), "text"
        if ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(str(path))
            return "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")), "text"
    except ImportError as exc:
        die(f"{path.name} needs an optional dependency: {exc.name}. Install requirements-analysis.txt")
    except Exception as exc:
        print(f"Skipping {path.name}: {exc}", file=sys.stderr)
    return None, "unknown"


def clean(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def analyze_table(df, name: str, args, out: Path, plt) -> dict[str, Any]:
    import numpy as np
    numeric = df.select_dtypes(include=np.number)
    summary: dict[str, Any] = {
        "file": name, "rows": int(len(df)), "columns": int(len(df.columns)),
        "column_names": [str(c) for c in df.columns],
        "missing_values": {str(k): int(v) for k, v in df.isna().sum().items() if int(v)},
        "duplicate_rows": int(df.duplicated().sum()),
        "numeric_summary": {}, "recommendations": [], "charts": [],
    }
    if not numeric.empty:
        desc = numeric.describe().T.replace({np.nan: None})
        summary["numeric_summary"] = {
            str(index): {str(k): clean(v) for k, v in row.items()} for index, row in desc.iterrows()
        }
        for column in numeric.columns:
            series = numeric[column].dropna()
            if len(series) > 1 and series.nunique() > 1:
                chart = out / f"{Path(name).stem}_{str(column).replace(' ', '_')[:35]}_hist.png"
                plt.figure(figsize=(8, 4.5)); plt.hist(series, bins=20, color="#8b5cf6", edgecolor="white")
                plt.title(f"Distribution: {column}"); plt.xlabel(str(column)); plt.ylabel("Count"); plt.tight_layout(); plt.savefig(chart, dpi=150); plt.close()
                summary["charts"].append(chart.name)
    for column, count in summary["missing_values"].items():
        if count: summary["recommendations"].append(f"Review missing values in '{column}' ({count:,} cells); document an imputation or exclusion rule.")
    if summary["duplicate_rows"]: summary["recommendations"].append(f"Investigate {summary['duplicate_rows']:,} duplicate rows before modeling or aggregation.")
    if not numeric.empty:
        summary["recommendations"].append("Validate units, outliers, and whether numeric columns are measures or identifiers before drawing conclusions.")
    if args.group_by and args.value and args.group_by in df.columns and args.value in df.columns:
        grouped = df.groupby(args.group_by, dropna=False)[args.value].sum().sort_values(ascending=False).head(args.top)
        chart = out / f"{Path(name).stem}_by_{args.group_by}.png"
        plt.figure(figsize=(9, 5)); grouped.sort_values().plot(kind="barh", color="#a855f7"); plt.title(f"{args.value} by {args.group_by}"); plt.xlabel(f"Sum of {args.value}"); plt.tight_layout(); plt.savefig(chart, dpi=150); plt.close()
        grouped.rename("value").reset_index().to_csv(out / f"{Path(name).stem}_grouped.csv", index=False)
        summary["charts"].append(chart.name)
        summary["grouping"] = {"group_by": args.group_by, "value": args.value, "top": [{"group": clean(k), "value": clean(v)} for k, v in grouped.items()]}
    return summary


def analyze_text(text: str, name: str) -> dict[str, Any]:
    words = text.split()
    lines = text.splitlines()
    return {"file": name, "characters": len(text), "lines": len(lines), "words": len(words), "recommendations": ["For stronger analysis, provide structured CSV/Excel/JSON data when possible."]}


def export_reports(report: dict, frames: list[tuple[str, Any]], out: Path, formats: set[str], raw_dir: Path) -> None:
    # Keep this function safe for callers that construct a minimal report object.
    report.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    report.setdefault("files", [])
    report.setdefault("executive_summary", "")
    pd, _ = imports()
    if "xlsx" in formats:
        with pd.ExcelWriter(out / "analysis.xlsx", engine="openpyxl") as writer:
            pd.DataFrame([{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in item.items()} for item in report["files"]]).to_excel(writer, sheet_name="Summary", index=False)
            for name, frame in frames:
                if hasattr(frame, "to_excel"):
                    frame.head(10000).to_excel(writer, sheet_name=Path(name).stem[:31], index=False)
    if "docx" in formats:
        from docx import Document
        doc = Document(); doc.add_heading("Purple Falcon Analysis Report", 0); doc.add_paragraph(report["generated_at"])
        doc.add_heading("Executive summary", 1); doc.add_paragraph(report["executive_summary"])
        for item in report["files"]:
            doc.add_heading(item["file"], 2); doc.add_paragraph(json.dumps(item, indent=2, ensure_ascii=False))
        for chart in out.glob("*.png"): doc.add_picture(str(chart), width=None)
        doc.save(out / "analysis.docx")
    if "pptx" in formats:
        from pptx import Presentation
        from pptx.util import Inches
        prs = Presentation(); slide = prs.slides.add_slide(prs.slide_layouts[0]); slide.shapes.title.text = "Purple Falcon Analysis"; slide.placeholders[1].text = report["executive_summary"]
        for chart in out.glob("*.png"):
            slide = prs.slides.add_slide(prs.slide_layouts[5]); slide.shapes.title.text = chart.stem; slide.shapes.add_picture(str(chart), Inches(0.6), Inches(1.2), width=Inches(9))
        prs.save(out / "analysis.pptx")
    (out / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    with zipfile.ZipFile(out / "purple_falcon_analysis.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in out.rglob("*"):
            if path.is_file() and path.name != "purple_falcon_analysis.zip": bundle.write(path, path.relative_to(out))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze files and create charts plus downloadable reports.")
    parser.add_argument("inputs", nargs="+", help="Files or directories")
    parser.add_argument("--out", default="purple_falcon_report", help="Output directory")
    parser.add_argument("--formats", nargs="+", default=["xlsx", "docx", "pptx"], choices=["xlsx", "docx", "pptx"], help="Report formats")
    parser.add_argument("--group-by", help="Categorical column for a bar chart")
    parser.add_argument("--value", help="Numeric column to aggregate for --group-by")
    parser.add_argument("--top", type=int, default=15, help="Maximum groups in the bar chart")
    args = parser.parse_args()
    pd, plt = imports(); out = Path(args.out).expanduser(); out.mkdir(parents=True, exist_ok=True); raw = out / "raw_files"; raw.mkdir(exist_ok=True)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "files": [], "executive_summary": ""}; frames = []
    for path in files_from(args.inputs):
        shutil.copy2(path, raw / path.name)
        data, kind = read_file(path, pd)
        if kind == "table" and data is not None:
            result = analyze_table(data, path.name, args, out, plt); frames.append((path.name, data))
        elif kind == "text" and data is not None: result = analyze_text(data, path.name)
        else: result = {"file": path.name, "status": "could not analyze"}
        report["files"].append(result)
    tables = [x for x in report["files"] if "rows" in x]
    report["executive_summary"] = f"Analyzed {len(report['files'])} file(s), including {len(tables)} structured dataset(s). " + (f"The datasets contain {sum(x['rows'] for x in tables):,} total rows. " if tables else "") + "Review missing data, duplicates, and chart context before making decisions."
    export_reports(report, frames, out, set(args.formats), raw)
    print(f"Done. Downloadable bundle: {out / 'purple_falcon_analysis.zip'}")


if __name__ == "__main__": main()
