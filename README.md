# QA Analytics Dashboard

Data-source agnostic **QA analytics** portfolio app built with **Streamlit**, **Pandas**, and **Plotly**.

Upload test execution results and defects from *any* website or project (CSV / JSON / Excel) using a standard schema — or click **Load demo data** to explore immediately.

**Live repo:** [github.com/Naser-Al-Noman/qa-dashboard](https://github.com/Naser-Al-Noman/qa-dashboard)

---

## Features

- **Home** — upload/demo data, shared filters, KPI cards (runs, pass %, duration, flaky tests, open defects)
- **Test Execution** — pass/fail/skip trends, duration drift, filterable run table, flaky-test detection
- **Defect Metrics** — severity donut, priority bars, MTTR by severity, burn-up, open-defect table
- **Trends** — suite × browser heatmap, failing-module Pareto, failure↔defect correlation, CSV export

---

## Screenshots

Add captures under `docs/screenshots/` using these filenames (placeholders are included):

| Page | File to add |
|------|-------------|
| Home / KPIs | `docs/screenshots/home.png` |
| Test Execution | `docs/screenshots/test-execution.png` |
| Defect Metrics | `docs/screenshots/defect-metrics.png` |
| Trends | `docs/screenshots/trends.png` |

```markdown
![Home](docs/screenshots/home.png)
![Test Execution](docs/screenshots/test-execution.png)
![Defect Metrics](docs/screenshots/defect-metrics.png)
![Trends](docs/screenshots/trends.png)
```

---

## Setup

**Requirements:** Python 3.10+ recommended.

```bash
# clone
git clone https://github.com/Naser-Al-Noman/qa-dashboard.git
cd qa-dashboard

# virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

1. Click **Load demo data** in the sidebar, **or**
2. Upload your own test/defect files → **Apply uploads**
3. Use sidebar filters, then open the pages under the sidebar navigation

---

## Project structure

```
qa-dashboard/
├── app.py                      # Home entry point
├── data/
│   ├── sample_data.py          # Faker-based demo generator
│   └── samples/                # Pre-generated CSV samples
├── docs/screenshots/           # Screenshot placeholders
├── pages/
│   ├── 1_Test_Execution.py
│   ├── 2_Defect_Metrics.py
│   └── 3_Trends.py
├── utils/
│   ├── loaders.py              # Upload, validation, filters
│   ├── metrics.py              # KPIs and analytics
│   ├── charts.py               # Plotly charts
│   └── ui.py                   # Shared page config / errors
├── requirements.txt
└── README.md
```

---

## CSV / JSON / Excel schema

Column names are normalized automatically (case-insensitive; spaces → underscores).  
Malformed rows (bad dates, invalid statuses) are **skipped with warnings** — the app should not crash.  
Missing **required** columns produce a clear error message.

### Test results — one row per execution

| Column | Required | Description |
|--------|----------|-------------|
| `run_id` | yes | Unique execution id |
| `timestamp` | yes | Run time (ISO or common date formats) |
| `website` | yes | Website / project name |
| `test_suite` | yes | Suite or module |
| `test_name` | yes | Test case name |
| `status` | yes | `pass` \| `fail` \| `skip` \| `blocked` |
| `duration_sec` | yes | Duration in seconds (numeric) |
| `browser` | yes | Browser name |
| `environment` | yes | e.g. staging, production, qa |
| `defect_id` | no | Linked defect id when applicable |
| `severity` | no | Severity when linked to a defect |

### Defects — one row per defect

| Column | Required | Description |
|--------|----------|-------------|
| `defect_id` | yes | Unique defect id |
| `title` | yes | Short summary |
| `severity` | yes | e.g. critical, high, medium, low |
| `priority` | yes | e.g. P0, P1, P2, P3 |
| `status` | yes | `open` \| `in-progress` \| `closed` |
| `created_date` | yes | When the defect was opened |
| `closed_date` | no | When closed (empty if still open) |
| `module` | yes | Area / module name (ideally matches `test_suite`) |

### Example `tests.csv`

```csv
run_id,timestamp,website,test_suite,test_name,status,duration_sec,browser,environment,defect_id,severity
RUN-1,2026-06-01 10:00:00,ShopFlow,Checkout,checkout_guest,pass,12.4,Chrome,staging,,
RUN-2,2026-06-01 10:01:00,ShopFlow,Checkout,checkout_card,fail,18.2,Chrome,staging,DEF-0001,high
```

### Example `defects.csv`

```csv
defect_id,title,severity,priority,status,created_date,closed_date,module
DEF-0001,[ShopFlow] Checkout card decline,high,P1,closed,2026-05-28,2026-06-02,Checkout
DEF-0002,[ShopFlow] Cart quantity bug,medium,P2,open,2026-06-10,,Cart
```

Supported uploads: **`.csv`**, **`.json`** (array or JSON Lines), **`.xlsx`** / **`.xls`**.

---

## Using your own data

1. Export runs from CI, Playwright, Cypress, TestRail, etc. into the test schema.
2. Export defects from Jira / Azure DevOps / Linear into the defect schema.
3. On Home, upload one or both files → **Apply uploads**.
4. Filter by website, environment, browser, and date range.
5. Download filtered CSV reports from Home, Test Execution, Defect Metrics, or Trends.

Align defect `module` with `test_suite` names so the Trends correlation view can link failures to open high-severity defects.

---

## Sample / demo data

```bash
python -m data.sample_data
```

Writes `data/samples/test_results.csv` and `data/samples/defects.csv` (~550 runs, ~55 defects, 90-day window, 3 websites). The sidebar **Load demo data** button generates the same data in memory.

---

## Notes

- Filters live in `st.session_state` and apply across all pages.
- Defects work standalone; optional `defect_id` on test rows enables linked-failure views.
- Portfolio / demo project — not connected to a live test-management API.

## License

MIT — feel free to fork and adapt for your portfolio or team demos.
