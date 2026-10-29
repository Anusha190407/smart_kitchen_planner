# 🍽️ Smart Kitchen Planner
### AI-Powered Meal Demand Forecasting, Inventory Optimization & Smart Replenishment

**Reduce food waste. Prevent stockouts. Make smarter purchasing decisions.**

Smart Kitchen Planner is a full-stack, AI-powered decision-support system designed for restaurants, commercial kitchens, college messes, and institutional dining facilities.

It connects meal demand forecasting, recipe-based ingredient planning, batch-level inventory tracking, supplier lead-time analysis, and interactive menu simulations in one responsive web application.

Instead of relying on guesswork or manual spreadsheets, kitchen managers can use historical demand and inventory data to anticipate future requirements, plan purchases, prioritize expiring ingredients, and make better operational decisions.

---

## 📌 Table of Contents

- [The Problem](#-the-problem)
- [Our Solution](#-our-solution)
- [Key Features](#-key-features)
- [How It Works](#-how-it-works)
- [AI/ML Forecasting Engine](#-aiml-forecasting-engine)
- [Smart Inventory Management](#-smart-inventory-management)
- [Interactive What-If Simulation](#-interactive-what-if-simulation)
- [Technology Stack](#-technology-stack)
- [System Architecture](#-system-architecture)
- [Project Structure](#-project-structure)
- [Installation and Setup](#-installation-and-setup)
- [Sample Data](#-sample-data)
- [Testing](#-testing)
- [Assumptions and Limitations](#-assumptions-and-limitations)
- [Future Enhancements](#-future-enhancements)

---

## 🚨 The Problem

Commercial kitchens must make daily decisions about how much food to prepare, which ingredients to purchase, and when to reorder supplies.

However, traditional kitchen management often faces several challenges:

- **Demand uncertainty:** Preparing too much food leads to waste, while preparing too little causes shortages.
- **Manual inventory management:** Spreadsheet-based tracking makes it difficult to monitor stock accurately.
- **Ingredient complexity:** A single meal may require multiple ingredients in different quantities.
- **Perishable inventory:** Ingredients can expire before they are consumed.
- **Supplier lead times:** Late purchasing decisions can leave kitchens without essential ingredients.
- **Lack of decision support:** Managers cannot easily evaluate how menu changes, discounts, or promotions affect future demand and inventory.

These challenges can increase operational costs, waste valuable food, and disrupt daily kitchen operations.

## 💡 Our Solution

Smart Kitchen Planner brings these decisions together in a single intelligent planning system.

The application predicts meal demand for the next seven days, converts meal forecasts into ingredient requirements, simulates inventory consumption using FIFO principles, and recommends when and how much to reorder.

Kitchen managers can also simulate menu price changes and promotions to understand their potential impact before making real-world decisions.

**The core idea:** Forecast what customers may order, calculate what the kitchen will need, and recommend what to purchase before shortages or expiry become problems.

---

## ✨ Key Features

### 1. 📈 AI-Powered Meal Demand Forecasting
- Forecasts demand for 51 meals over a rolling seven-day horizon.
- Uses historical order patterns, prices, discounts, and calendar information.
- Generates low, expected, and high demand estimates.
- Compares model performance against simple forecasting baselines.
- Flags meals with insufficient historical data as low confidence.

### 2. 🥗 Recipe-Based Ingredient Planning
- Converts predicted meal quantities into ingredient requirements.
- Aggregates ingredient demand across multiple meals.
- Identifies which meals contribute to each ingredient's demand.
- Helps kitchen managers plan procurement based on actual menu requirements.

### 3. 📦 FIFO Inventory Management
- Tracks inventory in batches with different expiry dates.
- Simulates consumption using First-In, First-Out (FIFO) principles, prioritizing the earliest-expiring stock.
- Accounts for shelf life and incoming supplier orders.
- Identifies ingredients at risk of expiry or stockout.

### 4. 🛒 Intelligent Reorder Recommendations
- Calculates projected stockout dates.
- Considers supplier lead times when determining reorder deadlines.
- Recommends purchase quantities based on forecast demand, safety stock, and available inventory.
- Flags urgent or overdue purchases.
- Limits recommendations for perishable items to reduce potential spoilage.

### 5. 🔔 Real-Time Alerts and Dashboard
- Highlights low-stock ingredients and projected shortages.
- Identifies stock approaching expiry.
- Provides a prioritized “Use First” queue.
- Displays operational KPIs and planning alerts in one place.

### 6. 🔄 Interactive What-If Menu Simulation
- Simulates menu price changes and promotional scenarios.
- Evaluates potential changes in meal demand.
- Helps managers explore alternative menu strategies before committing to them.

### 7. 📊 Reports and Data Management
- Imports and validates Excel and CSV datasets.
- Exports data templates for easier data preparation.
- Generates purchase orders in Excel and PDF formats.
- Supports savings audits and operational reporting.

### 8. 🔐 Restaurant Accounts and Data Persistence
- Supports account creation and login.
- Uses password hashing and signed JWT sessions.
- Stores application data in a local SQLite database.
- Provides sample-data loading for demonstration and testing.

---

## ⚙️ How It Works

The application follows a connected planning workflow.

1. **Historical data:** Load meal orders, recipes, ingredient details, inventory, and supplier information.
2. **Demand forecasting:** Predict expected meal orders for the next seven days.
3. **Ingredient calculation:** Convert meal-level forecasts into ingredient-level demand.
4. **Inventory simulation:** Project stock levels over time, considering expiry dates and incoming deliveries.
5. **Purchase planning:** Calculate reorder deadlines and suggested quantities.
6. **Decision support:** Review alerts, reports, and menu simulations to make informed decisions.

### Example Workflow

Suppose a kitchen expects to serve more chicken-based meals over the coming week.

The planner can:

- Forecast the expected number of orders for those meals.
- Calculate the total chicken required using the associated recipes.
- Compare the requirement against current stock and incoming deliveries.
- Estimate when the available stock may run out.
- Account for the supplier's delivery lead time.
- Recommend an appropriate reorder quantity and highlight urgency.

This connects meal planning directly to purchasing decisions.

---

## 🤖 AI/ML Forecasting Engine

The forecasting engine predicts daily meal demand (`num_orders`) for 51 meals over a seven-day rolling horizon.

### Model Approach

The system uses a global Poisson Gradient Tree Boosting approach for count-based demand forecasting.

Poisson-based modeling is suitable for non-negative order counts because it models the expected demand as a non-negative quantity.

The model minimizes Poisson deviance:

\[
D = 2\sum_i \left[y_i\log\left(\frac{y_i}{\mu_i}\right)-(y_i-\mu_i)\right]
\]

Here:

- \(y_i\) represents actual meal demand.
- \(\mu_i\) represents predicted meal demand.

### Features Used

| Feature group | Examples | Purpose |
|---|---|---|
| Historical demand | `lag_7`, `lag_14` | Capture recent weekly demand patterns |
| Rolling statistics | 7-day mean, 7-day standard deviation, 28-day mean | Understand demand levels and variability |
| Pricing | Price ratio, discount percentage | Capture price and promotional signals |
| Calendar | Day of week, day of month, week of year, weekend flag | Capture recurring demand patterns |
| Meal identity | Meal ID, category, cuisine | Learn differences between meal types |

Meal names are excluded from the model features.

### Preventing Data Leakage

A forecasting model should not use future information that would be unavailable when making a real prediction.

Smart Kitchen Planner applies a seven-day anchor rule. For a target date \(T\), historical demand features use information no later than \(T-7\).

For example:

- `lag_7` uses demand from \(T-7\).
- `lag_14` uses demand from \(T-14\).
- `rolling_mean_7` uses the seven-day window from \(T-13\) through \(T-7\).
- `rolling_mean_28` uses the 28-day window from \(T-34\) through \(T-7\).

This supports consistent multi-day forecasting without incorporating demand observed after the forecast anchor.

### Validation and Baselines

The model uses a chronological train-validation split:

- **Training:** Historical data excluding the final 14 days.
- **Validation:** The final 14 historical days.

Performance is compared against two baselines:

1. Same weekday in the previous week (`lag_7`).
2. The previous 28-day rolling average.

The system evaluates forecasts using:

- **WAPE:** Weighted Absolute Percentage Error.
- **MAE:** Mean Absolute Error.
- **MAPE:** Mean Absolute Percentage Error.

These metrics help evaluate forecast accuracy from different perspectives. MAPE can be undefined or unstable when actual demand is zero or very small, so it should be interpreted carefully.

### Demand Confidence and Uncertainty

The system generates low, expected, and high demand estimates using 10th- and 90th-quantile estimators alongside the expected forecast.

Meals with fewer than 28 days of historical data fall back to their category's day-of-week average and receive a **Low Confidence** label.

The resulting estimates help kitchen managers plan for different demand scenarios rather than relying on a single prediction.

---

## 📦 Smart Inventory Management

### FIFO-Based Batch Simulation

FIFO stands for **First In, First Out**. It is an inventory management principle that prioritizes older stock for consumption before newer stock.

The system simulates inventory using batch-level expiry information.

Each ingredient's inventory is represented using:

- The earliest batch and its expiry date.
- The remaining stock and its assumed expiry date.
- Incoming supplier orders and their expected arrival dates.
- Projected ingredient consumption over the planning horizon.

### Inventory Planning Workflow

1. Start with the current stock.
2. Separate the earliest batch from the remaining inventory.
3. Project ingredient consumption based on forecast demand and recipe requirements.
4. Consume the earliest-expiring batches first.
5. Add incoming orders when they arrive.
6. Track projected stockouts and expiry risks.
7. Generate reorder recommendations.

### Reorder Deadline

The reorder deadline is calculated using the projected stockout date and the supplier's lead time:

**Order-by date = Projected stockout date − Supplier lead time**

If the deadline is today or earlier, the purchase is flagged as urgent or overdue.

### Suggested Purchase Quantity

The suggested quantity is based on:

- Forecast demand during the coverage window.
- Required safety stock.
- Available inventory.
- Incoming stock that has not yet arrived.

Conceptually:

**Suggested quantity = Maximum of 0 and (Forecast demand + Safety stock − Available stock − Incoming stock)**

The implementation also applies a perishable-stock cap to reduce the risk of purchasing more than can reasonably be consumed within the ingredient's shelf life.

### Why This Matters

This approach connects forecasting with inventory operations. It helps managers identify what to purchase, when to purchase it, and which ingredients need attention first.

---

## 🔄 Interactive What-If Simulation

Kitchen planning decisions often involve trade-offs.

For example:

- What happens if the price of a meal changes?
- How might a promotion affect expected demand?
- Will a proposed menu change increase ingredient requirements?
- Could a new scenario increase stockout risk or waste?

The What-If module allows managers to explore price and promotional scenarios through the application's simulation engine.

It supports better-informed decisions by making the potential consequences of a menu change easier to evaluate.

**Note:** Scenario outputs are model-based estimates, not guarantees of actual customer behavior.

---

## 🏗️ Technology Stack

| Component | Technologies |
|---|---|
| Frontend | HTML5, CSS3, JavaScript |
| Backend | Python, FastAPI |
| Machine Learning | NumPy, SciPy, Pandas, local gradient-boosting and quantile-model implementations |
| Database | SQLite |
| Data Processing | Pandas, OpenPyXL |
| Reporting | ReportLab, OpenPyXL |
| Authentication | Password hashing, JWT sessions |
| Visualization | Interactive dashboard charts and SVG graphics |
| Testing | Python automated tests with pytest-compatible test structure |

The application is designed to run locally without requiring external network access for its core forecasting, data processing, reporting, and visualization workflows.

---

## 🧩 System Architecture

```text
                 ┌─────────────────────────┐
                 │     Kitchen Manager     │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │   Web Application UI    │
                 │ HTML, CSS, JavaScript   │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │      FastAPI Backend    │
                 └────────────┬────────────┘
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
      ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
      │ AI/ML Demand│  │  Ingredient │  │  Inventory  │
      │ Forecasting │  │  Calculation│  │  & FIFO     │
      └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
             │                │                │
             └────────────────┼────────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │  Reorder & Alert Engine │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │ Dashboard, What-If &    │
                 │ Excel/PDF Reports       │
                 └─────────────────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │       SQLite DB         │
                 └─────────────────────────┘
```

---

## 📁 Project Structure

```text
smart_kitchen_planner/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── auth.py
│   ├── data_manager.py
│   ├── forecasting.py
│   ├── ingredients.py
│   ├── inventory.py
│   ├── alerts.py
│   ├── whatif.py
│   ├── reports.py
│   └── tests/
│       └── test_logic.py
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       └── app.js
├── data/
│   ├── smart_kitchen_dataset.xlsx
│   ├── meals.csv
│   ├── daily_orders.csv
│   ├── next_7_days_inputs.csv
│   ├── recipes.csv
│   ├── ingredient_master.csv
│   ├── inventory_history.csv
│   └── current_stock.csv
├── models/
│   └── Versioned trained-model JSON artifacts
├── smart_kitchen.db
├── run_server.sh
└── README.md
```

### Important Modules

| Module | Responsibility |
|---|---|
| `main.py` | API endpoints, request handling, and application serving |
| `database.py` | SQLite database and schema management |
| `auth.py` | Password hashing and authentication sessions |
| `data_manager.py` | CSV/Excel import, validation, and templates |
| `forecasting.py` | Meal demand prediction and model evaluation |
| `ingredients.py` | Recipe-based ingredient demand calculation |
| `inventory.py` | FIFO inventory projection and reorder suggestions |
| `alerts.py` | Dashboard KPIs, alerts, and expiry prioritization |
| `whatif.py` | Menu price and promotion simulations |
| `reports.py` | Purchase orders and reporting |

---

## 🚀 Installation and Setup

### Prerequisites

Install the following before starting:

- Python 3.10 or later, compatible with the project's dependencies.
- Git, if cloning the repository.
- A terminal or command-line interface.

### Step 1: Clone the Repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd smart_kitchen_planner
```

Replace `<YOUR_REPOSITORY_URL>` with the actual GitHub repository URL.

### Step 2: Start the Application

On Linux or macOS, or in a compatible shell:

```bash
chmod +x run_server.sh
./run_server.sh
```

Alternatively, start the FastAPI server directly:

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Make sure the project's required Python dependencies are installed before launching the application. If a dependency file is provided, install from that file.

### Step 3: Open the Web Application

Visit:

**http://localhost:8000**

The application should open in your browser when the server starts successfully.

### Step 4: Sign In or Create an Account

The supplied demonstration account is:

- **Email:** `chef@spicegarden.com`
- **Password:** `admin123`

Alternatively, use the registration option to create an account.

> **Security note:** The credentials above are for local demonstration only. Do not use default credentials in a public or production deployment.

### Step 5: Load Sample Data

Use the **Load Sample Data** button in the application to initialize the demonstration dataset and explore the forecasting, inventory, alert, and reporting workflows.

---

## 🧪 Sample Data

The project includes a sample dataset for demonstrating the end-to-end planning workflow.

| Dataset | Purpose |
|---|---|
| `meals.csv` | Meal information and categories |
| `daily_orders.csv` | Historical meal demand |
| `next_7_days_inputs.csv` | Inputs for future demand forecasting |
| `recipes.csv` | Meal-to-ingredient relationships |
| `ingredient_master.csv` | Ingredient properties and shelf life |
| `inventory_history.csv` | Historical inventory information |
| `current_stock.csv` | Opening stock and batch information |
| `smart_kitchen_dataset.xlsx` | Consolidated workbook containing seven sheets |

The dataset is intended to demonstrate how meal forecasts are transformed into ingredient requirements and replenishment decisions.

### Demonstration Scenarios

Judges can explore the following scenarios:

1. **Demand planning:** Review predicted meal requirements for the next seven days.
2. **Stockout prevention:** Examine ingredients that require immediate replenishment.
3. **Expiry management:** Review the prioritized Use First queue.
4. **Purchase planning:** Inspect suggested quantities and order-by dates.
5. **Menu simulation:** Experiment with different prices and promotions.
6. **Reporting:** Generate purchase orders and review planning outputs.

---

## ✅ Testing

Automated tests are located in:

```text
backend/tests/test_logic.py
```

Run the test suite from the project root:

```bash
python3 -m pytest backend/tests/ -v
```

The test suite is intended to verify core planning logic, including forecasting-related calculations and inventory or replenishment rules.

For a reliable demonstration, run the tests in the same environment and with the dependencies used by the application.

---

## ⚠️ Assumptions and Limitations

Transparency is important when using forecasts to make operational decisions. The following assumptions apply to the current implementation.

### 1. Inventory Batch Expiry

The source data provides the earliest batch's expiry date but does not specify expiry dates for all remaining stock.

The simulation assumes:

- The earliest batch uses its supplied expiry date.
- The remaining stock expires at the as-of date plus the ceiling of half its shelf life.
- The assumed expiry is bounded so it does not precede the earliest batch's expiry.

These are modeling assumptions rather than verified expiry dates for every physical batch.

### 2. Initial Stock for Selected Ingredients

In the supplied `current_stock.csv`, chicken and fish fillet have zero opening stock.

The application highlights these items as urgent replenishment requirements. Actual purchasing decisions should still be verified against the physical inventory.

### 3. Operational Date

The planning engine defines its operational “Today” as the day after the latest date recorded in `Daily_Orders`.

When new daily orders are committed, the planning date advances and forecasting horizons are recalculated according to the application's update logic.

This simulation date may differ from the real calendar date.

### 4. Forecast Uncertainty

Historical demand patterns cannot fully predict unprecedented events, such as supply disruptions, sudden changes in customer behavior, or unexpected events.

Low and high estimates should be interpreted as model-based planning ranges, not guaranteed minimum and maximum demand.

### 5. Single-Facility Planning

The current system focuses on an individual restaurant, mess, or institutional kitchen. It does not implement multi-warehouse stock transfers or centralized distribution across multiple facilities.

### 6. Notifications

The settings interface supports notification recipients and alert configuration, while the current deployment delivers notifications through the in-app alert center rather than an external email delivery service.

### 7. Local Deployment

The application is designed around local execution. External services and production infrastructure are not required for the core demonstration workflow, although initial environment setup may require the appropriate dependencies.

---

## 🔮 Future Enhancements

Potential improvements include:

- Integration with live point-of-sale systems for continuous demand updates.
- Supplier APIs for availability checks and automated purchase orders.
- Email, SMS, or messaging-based notifications.
- Multi-location inventory and centralized procurement.
- Advanced demand models incorporating weather, events, holidays, and local trends.
- Improved model monitoring and automated retraining reports.
- Ingredient substitution recommendations during supply shortages.
- Food-waste analytics and sustainability reporting.
- Cloud deployment with role-based access controls and secure production configuration.

These are proposed enhancements and are not represented as completed features.

---

## 🌱 Impact and Value

Smart Kitchen Planner aims to make kitchen operations more data-driven by connecting demand forecasting with inventory and purchasing decisions.

Its potential benefits include:

- **Reduced food waste:** Better alignment between expected demand and ingredient purchasing.
- **Fewer stockouts:** Earlier identification of upcoming shortages.
- **Improved purchasing:** Reorder recommendations that account for demand, available stock, and supplier lead times.
- **Better inventory rotation:** FIFO simulation and expiry prioritization.
- **Faster decisions:** Centralized dashboards, alerts, simulations, and reports.
- **More transparent planning:** Explicit assumptions and uncertainty estimates.

Actual savings and waste reduction depend on forecast accuracy, data quality, operational practices, and the actions taken by kitchen managers. Quantified impact should be reported only after measurement against a suitable baseline.

---

## 🏆 Why Smart Kitchen Planner?

Unlike a standalone demand predictor or a basic inventory tracker, Smart Kitchen Planner connects the entire planning process:

**Meal Demand → Ingredient Requirements → Inventory Projection → Reorder Recommendations → Operational Decisions**

This integrated approach helps transform historical data into practical, explainable purchasing decisions for kitchens.

---

## 👥 Contributors

- **Project Team:** Anusha S,Helena Vince J, Karthika I,Shree Supriya S,Raja Sri S.
- **Project Name:** Smart Kitchen Planner
- **Category:** AI/ML · Full-Stack Development · Inventory Optimization · Food-Waste Reduction

---

**Smart Kitchen Planner — Plan smarter. Waste less. Serve better.** 🍽️
