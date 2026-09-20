# Integrated web UI

The original chat remains available, with a new **📊 Data Analysis & Reports** tab.

Install the existing chat dependencies plus the analysis dependencies:

```bash
python -m pip install -r requirements-analysis.txt
```

Launch the integrated application:

```bash
python purple_falcon_app.py
```

The analysis tab accepts CSV, TSV, JSON, Excel, PDF, Word, PowerPoint, TXT, MD, and LOG files. It can generate charts, descriptive summaries, data-quality recommendations, and downloadable Excel, Word, PowerPoint, JSON, PNG, raw-file, and ZIP outputs.

For grouped bar charts, provide both **Group-by column** and **Numeric value column**, for example `Region` and `Sales`.
