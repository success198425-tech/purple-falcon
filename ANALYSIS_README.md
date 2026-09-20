# Purple Falcon data analysis command

`data_analyzer.py` is a standalone command-line tool for attachments and files. It analyzes CSV, TSV, JSON, Excel, text, PDF, DOCX, and PPTX inputs; creates statistical summaries and PNG charts; and exports Excel, Word, and PowerPoint reports.

## Install

```bash
python -m pip install -r requirements-analysis.txt
```

## Run

Analyze one file and create all report formats:

```bash
python data_analyzer.py data/sales.csv --out reports/sales
```

Analyze a folder (including nested files):

```bash
python data_analyzer.py attachments/ --out reports/attachments
```

Create a bar chart by category and export selected formats:

```bash
python data_analyzer.py sales.xlsx --group-by Region --value Revenue --top 10 --formats xlsx pptx
```

Each run writes:

- `analysis.xlsx` — summary and source tables
- `analysis.docx` — narrative report with charts
- `analysis.pptx` — presentation with chart slides
- `analysis.json` — raw machine-readable findings
- `*.png` and grouped CSV files — charts and intermediate data
- `raw_files/` — copies of the original inputs
- `purple_falcon_analysis.zip` — downloadable bundle containing everything

The generated statistics are descriptive, not proof of causation. Validate data quality, units, privacy, and sampling before using the results for decisions. The tool does not send files to an AI service.
