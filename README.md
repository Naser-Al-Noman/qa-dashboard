# QA Analytics Dashboard

Data-source agnostic Streamlit dashboard for **test execution** and **defect** analytics. Upload CSV/JSON in a standard schema (any website/project), or explore with built-in sample data.

## Features

- Test metrics: pass/fail/skip/blocked rates, duration, top failing tests
- Defect metrics: severity/priority/module breakdown, resolution time, create vs close trends
- Interactive Plotly charts
- Shared filters: website/project, environment, browser, date range
- Sample data loader and CSV export of filtered views

## Quick start

```bash
cd qa-dashboard
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`), then click **Load sample data** on Home.

## Project structure

```
qa-dashboard/
├── app.py                 # Home: upload, filters, KPI overview
├── data/sample_data.py    # Multi-website sample generator
├── utils/loaders.py       # Upload, validation, shared filters
├── utils/metrics.py       # Aggregations and KPIs
├── utils/charts.py        # Plotly chart builders
├── pages/
│   ├── 1_Test_Execution.py
│   ├── 2_Defect_Metrics.py
│   └── 3_Trends.py
├── requirements.txt
└── README.md
```

## Standard schemas

### Test execution results (one row per run)

| Column | Required | Description |
|--------|----------|-------------|
| `run_id` | yes | Unique execution id |
| `timestamp` | yes | Run time (ISO or common date formats) |
| `website` | yes | Website / project name |
| `test_suite` | yes | Suite or module |
| `test_name` | yes | Test case name |
| `status` | yes | `pass` / `fail` / `skip` / `blocked` |
| `duration_sec` | yes | Duration in seconds |
| `browser` | yes | Browser name |
| `environment` | yes | e.g. staging, production, qa |
| `defect_id` | no | Linked defect when applicable |
| `severity` | no | Severity when linked to a defect |

### Defects (one row per defect)

| Column | Required | Description |
|--------|----------|-------------|
| `defect_id` | yes | Unique defect id |
| `title` | yes | Short summary |
| `severity` | yes | e.g. critical, high, medium, low |
| `priority` | yes | e.g. P0, P1, P2, P3 |
| `status` | yes | `open` / `in-progress` / `closed` |
| `created_date` | yes | When the defect was opened |
| `closed_date` | no | When closed (null if still open) |
| `module` | yes | Area / module name |

Column names are normalized (case-insensitive; spaces → underscores). Status values are lowercased. Invalid rows are dropped with on-screen warnings; missing **required** columns fail the upload.

## Using your own data

1. Export results from your CI, TestRail, Playwright report, Jira, etc. into the schemas above.
2. On Home, upload test and/or defect files (CSV or JSON).
3. Click **Apply uploads**.
4. Use the sidebar filters; open the detail pages for charts and trends.
5. Export the filtered tables via the download buttons.

### Minimal CSV examples

**tests.csv**

```csv
run_id,timestamp,website,test_suite,test_name,status,duration_sec,browser,environment,defect_id,severity
RUN-1,2026-06-01 10:00:00,ShopFlow,Checkout,checkout_guest,pass,12.4,Chrome,staging,,
RUN-2,2026-06-01 10:01:00,ShopFlow,Checkout,checkout_card,fail,18.2,Chrome,staging,DEF-0001,high
```

**defects.csv**

```csv
defect_id,title,severity,priority,status,created_date,closed_date,module
DEF-0001,[ShopFlow] Checkout card decline,high,P1,closed,2026-05-28,2026-06-02,Checkout
DEF-0002,[ShopFlow] Cart quantity bug,medium,P2,open,2026-06-10,,Cart
```

## Sample data

`data/sample_data.py` uses **Faker** to generate:

- 550+ test runs across 3 websites × 4 suites, mixed statuses, timestamps over the last 90 days
- 55+ defects, many linked to failed/blocked runs via `defect_id`

```bash
python -m data.sample_data
```

This writes CSVs to `data/samples/test_results.csv` and `data/samples/defects.csv`. The Home page **Load sample data** button calls `generate_sample_data()` in memory.

## Notes

- Defects work standalone; when `defect_id` matches test rows, the dashboard shows linked failure summaries.
- Filters are stored in `st.session_state` and apply across all pages.
- This is a portfolio / demo project — not wired to a live test management system.
