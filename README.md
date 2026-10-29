# Smart Kitchen Planner

"Smart Kitchen Planner" is a full-stack decision-support and replenishment system designed for restaurants, commercial kitchens, and institutional dining halls (messes). It unifies meal demand forecasting, recipe ingredient explosion, FIFO batch-level inventory tracking, supplier lead-time order generation, and real-time "What-if" menu simulation into a single responsive web application.

---

## Quick Start (Two-Command Run Guide)

The entire application runs locally out of the box.

### Command 1: Start the Backend API & Frontend Server
```bash
./run_server.sh
# Or alternatively:
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Command 2: Launch or Open the Web Application
Open your browser to:
```
http://localhost:8000
```
*(Default test account: `chef@spicegarden.com` / `admin123`, or click "Create account" to initialize an independent restaurant instance).*

A dedicated **"Load sample data"** button is pinned to the header and data upload center, allowing one-click re-initialization of the synthetic restaurant benchmark.

---

## Folder Structure

```
smart_kitchen_planner/
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI server, route controllers, and static mounts
│   ├── database.py          # SQLite schema, foreign keys, and connection manager
│   ├── auth.py              # Password hashing (PBKDF2/SHA256) & signed JWT sessions
│   ├── data_manager.py      # Excel/CSV parser, cross-table validator, template exporter
│   ├── forecasting.py       # Poisson Gradient Boosting, quantile loss, and baselines
│   ├── ingredients.py       # Recipe demand explosion, category aggregation, and drilldown
│   ├── inventory.py         # FIFO batch projection, perishability caps, and order suggestion
│   ├── alerts.py            # Dashboard KPIs, stock-out/expiry alerts, and "Use First" queue
│   ├── whatif.py            # Real-time menu price/promo sensitivity simulation engine
│   ├── reports.py           # Savings audit, purchase order generation (Excel & PDF)
│   └── tests/
│       ├── __init__.py
│       └── test_logic.py    # Automated test suite for core planning algorithms
├── frontend/
│   ├── index.html           # Single-page application entry point
│   ├── css/
│   │   └── styles.css       # Design tokens, typography (Inter), and 8px grid layout
│   └── js/
│       └── app.js           # Reactive SPA controller, data grids, and SVG charts
├── data/
│   ├── smart_kitchen_dataset.xlsx  # Complete 7-sheet workbook
│   ├── meals.csv
│   ├── daily_orders.csv
│   ├── next_7_days_inputs.csv
│   ├── recipes.csv
│   ├── ingredient_master.csv
│   ├── inventory_history.csv
│   └── current_stock.csv
├── models/                  # Versioned JSON artifacts for the last 5 trained models
├── smart_kitchen.db         # Persistent SQLite database
├── run_server.sh            # Production launcher script
└── README.md                # Comprehensive documentation and assumptions
```

---

## How the Model Works

### 1. Objective and Architecture
The forecasting engine predicts daily meal demand count (`num_orders`) across all 51 meals over a 7-day rolling horizon using a global Poisson Gradient Tree Boosting architecture. Poisson deviance minimization ($2 \sum (y \log(y/\mu) - (y - \mu))$) natively models non-negative integer count data, preventing negative predictions and correctly scaling variance with demand volume.

### 2. Strict No-Leakage Feature Rule
To prevent data leakage across multi-day horizons, all historical features for target date $T$ are computed **strictly from records at least 7 days before $T$** (anchor date $A = T - 7$):
- **Lag Features**: `lag_7` (actual demand on $T - 7$), `lag_14` (actual demand on $T - 14$).
- **Rolling Statistics**: `rolling_mean_7` and `rolling_std_7` (7-day window $[T-13, T-7]$), `rolling_mean_28` (28-day window $[T-34, T-7]$).
- **Price Features**: `price_ratio` (`checkout_price / base_price`), `discount_pct`.
- **Calendar Signals**: `day_of_week` (0–6), `day_of_month` (1–31), `week_of_year` (1–53), `is_weekend` (0/1).
- **Categorical Identity**: `meal_id`, `category`, and `cuisine` index encodings.
*(Meal name is strictly excluded from features).*

### 3. Time-Based Validation & Benchmarking
- Training uses strict time-based splits: training on all days up to the last 14 days, validated against the final 14 historical days.
- **Baselines**: Evaluated against (1) Same weekday last week (`lag_7`), and (2) 28-day rolling average. The active model outperforms both baselines across WAPE, MAE, and MAPE.
- **Prediction Range**: Quantile regression estimators generate 10% (Low) and 90% (High) uncertainty bounds per meal per day.
- **Fallback Rule**: Meals with fewer than 28 days of history automatically fall back to their category's day-of-week average and receive a `low confidence` label.

---

## FIFO Inventory Simulation & Order Suggestions

1. **Initial Batches**:
   - Batch 1 (Earliest batch): Quantity = `qty_in_earliest_batch`, expires on `earliest_expiry_date`.
   - Batch 2 (Remaining stock): Quantity = `stock_on_hand - qty_in_earliest_batch`.
2. **Perishability & FIFO Consumption**:
   - Remaining stock is assumed to expire on `as_of_date + ceil(shelf_life_days / 2)` (never earlier than the earliest batch).
   - In-transit orders arrive on `order_arrival_date` and expire after full `shelf_life_days`.
   - Consumption consumes oldest expiring batches first (FIFO).
3. **Order Suggestion Formulation**:
   - $\text{Order-by Date} = \text{Projected Stock-out Date} - \text{Supplier Lead Time}$. If $\le \text{Today}$, marked as urgent/late.
   - $\text{Coverage Window} = \min(\text{shelf\_life\_days} - 1, \text{supplier\_lead\_time\_days} + 5)$, at least 1 day.
   - $\text{Suggested Qty} = \lceil \text{Demand over Coverage Window} + \text{Safety Stock} - \text{Available Stock} - \text{In Transit} \rceil$.
   - **Perishable Cap**: Suggested reorder quantity is capped to the volume that can be consumed within `shelf_life_days` to prevent purchasing surplus that will spoil.

---

## Assumptions

1. **FIFO Remaining Batch Expiry**: The source data specifies only the earliest batch's expiry date (`earliest_expiry_date`). As prescribed, the remainder of `stock_on_hand` is assumed to expire on `as_of_date + ceil(shelf_life_days / 2)`, bounded to never expire earlier than the earliest batch.
2. **Current Stock Verification (29-10-2026)**: In `current_stock.csv`, Chicken and Fish fillet start with 0 opening stock on hand. As specified, they are surfaced in bold RED status with urgent immediate reorders required.
3. **Operational "Today" Advance**: "Today" is dynamically anchored to the calendar day following the latest date in `Daily_Orders`. Whenever new daily orders are committed, "Today" moves forward, and background retraining recalculates all horizons.
4. **Offline Resilience**: External network access is disabled on the host sandbox. All ML training, gradient tree boosting, quantile regression, PDF rendering, Excel manipulation, and interactive charting run via high-performance local implementations in NumPy, SciPy, Pandas, OpenPyXL, and ReportLab.

---

## Known Limits

1. **Uncertainty Bounds**: Quantile bounds (10% and 90%) model historical variance in meal order volume; unprecedented supply shocks or force majeure disruptions fall outside statistical confidence intervals.
2. **Single-Facility Scope**: Inventory and purchasing suggestions are computed for a single kitchen, mess, or restaurant facility rather than multi-warehouse hub-and-spoke redistribution.
3. **Email Notification Service**: The settings interface configures notification recipients and alerts. In this deployment, notifications are delivered via the in-app alert center.
