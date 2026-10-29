import os
import io
import json
import uuid
import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.database import init_db, get_db
from backend.auth import hash_password, verify_password, create_jwt_token, get_current_user
from backend.data_manager import (
    load_sample_dataset_for_restaurant, validate_sheet_data, 
    get_sheet_template, REQUIRED_COLUMNS, parse_date_str, get_app_today_date
)
from backend.forecasting import (
    train_and_evaluate_model, get_meal_forecast_data, 
    get_meal_history_and_forecast, update_next_7_days_forecast
)
from backend.ingredients import calculate_ingredient_forecast
from backend.inventory import run_inventory_simulation
from backend.alerts import get_dashboard_data
from backend.whatif import simulate_what_if_scenario, apply_what_if_scenario, get_use_it_first_suggestions
from backend.reports import (
    calculate_savings_report, generate_purchase_orders_excel, 
    generate_purchase_orders_pdf, export_table_to_excel
)
import pandas as pd

app = FastAPI(title="Smart Kitchen Planner API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup DB init
@app.on_event("startup")
def startup_event():
    init_db()

# --- Pydantic Request Models ---
class RegisterRequest(BaseModel):
    restaurant_name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class SheetSaveRequest(BaseModel):
    rows: List[Dict[str, Any]]

class AddTodayRequest(BaseModel):
    date: str
    orders: List[Dict[str, Any]] # meal_id, num_orders, checkout_price
    stocks: List[Dict[str, Any]] # ingredient, stock_on_hand, earliest_expiry_date, qty_in_earliest_batch, order_in_transit_qty, order_arrival_date

class WhatIfSimulateRequest(BaseModel):
    meal_id: int
    date: str
    checkout_price: float
    promo_active: int
    featured_on_menu: int
    festival_or_event: int

class WhatIfApplyRequest(BaseModel):
    meal_id: int
    date: str
    checkout_price: float
    promo_active: int
    featured_on_menu: int
    festival_or_event: int
    simulated_orders: float

class ExportTableRequest(BaseModel):
    table_name: str
    columns: List[str]
    rows: List[Dict[str, Any]]

class SettingsRequest(BaseModel):
    email_alerts_enabled: bool
    alert_email: Optional[str] = None
    notify_stockout: bool = True
    notify_expiry: bool = True
    notify_arrival: bool = True

# --- Background Task Helper ---
def trigger_full_recalculation(restaurant_id: str):
    """Retrains the model, updates forecasts, inventory projections and order suggestions."""
    train_and_evaluate_model(restaurant_id)
    with get_db() as conn:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE restaurants SET last_updated = ? WHERE id = ?", (now_str, restaurant_id))

# --- Auth Endpoints ---
@app.post("/api/auth/register")
def register(req: RegisterRequest):
    if not req.restaurant_name.strip() or not req.email.strip() or not req.password:
        raise HTTPException(status_code=400, detail="All fields are required")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (req.email.strip().lower(),))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Account with this email already exists")
            
        restaurant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("INSERT INTO restaurants (id, name, created_at, last_updated) VALUES (?, ?, ?, ?)",
                       (restaurant_id, req.restaurant_name.strip(), now_str, now_str))
        cursor.execute("INSERT INTO users (id, email, password_hash, restaurant_id, created_at) VALUES (?, ?, ?, ?, ?)",
                       (user_id, req.email.strip().lower(), hash_password(req.password), restaurant_id, now_str))
        cursor.execute("INSERT INTO settings (restaurant_id, alert_email) VALUES (?, ?)", (restaurant_id, req.email.strip().lower()))

    # Auto-seed sample data on registration for a seamless out-of-the-box experience
    load_sample_dataset_for_restaurant(restaurant_id)
    train_and_evaluate_model(restaurant_id)

    token = create_jwt_token({"user_id": user_id, "restaurant_id": restaurant_id, "email": req.email.strip().lower()})
    return {
        "token": token,
        "user": {"id": user_id, "email": req.email.strip().lower()},
        "restaurant": {"id": restaurant_id, "name": req.restaurant_name.strip(), "last_updated": now_str}
    }

@app.post("/api/auth/login")
def login(req: LoginRequest):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.email, u.password_hash, u.restaurant_id, r.name as restaurant_name, r.last_updated
            FROM users u JOIN restaurants r ON u.restaurant_id = r.id
            WHERE u.email = ?
        """, (req.email.strip().lower(),))
        row = cursor.fetchone()
        
    if not row or not verify_password(req.password, row['password_hash']):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    token = create_jwt_token({"user_id": row['id'], "restaurant_id": row['restaurant_id'], "email": row['email']})
    return {
        "token": token,
        "user": {"id": row['id'], "email": row['email']},
        "restaurant": {"id": row['restaurant_id'], "name": row['restaurant_name'], "last_updated": row['last_updated']}
    }

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return user

# --- Data Management Endpoints ---
@app.post("/api/data/load-sample")
def load_sample_data(background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    restaurant_id = user["restaurant_id"]
    load_sample_dataset_for_restaurant(restaurant_id)
    # Train immediately so user sees full populated data
    train_and_evaluate_model(restaurant_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_updated FROM restaurants WHERE id = ?", (restaurant_id,))
        row = cursor.fetchone()
        last_updated = row['last_updated'] if row else ""
        
    return {"status": "success", "message": "Sample dataset loaded and model trained successfully", "last_updated": last_updated}

@app.get("/api/data/template/{sheet_name}")
def download_template(sheet_name: str):
    try:
        content = get_sheet_template(sheet_name)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={sheet_name}_template.xlsx"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/data/sheet/{sheet_name}")
def get_sheet_data(sheet_name: str, user: dict = Depends(get_current_user)):
    restaurant_id = user["restaurant_id"]
    table_map = {
        "Meals": "meals",
        "Daily_Orders": "daily_orders",
        "Next_7_Days_Inputs": "next_7_days_inputs",
        "Recipes": "recipes",
        "Ingredient_Master": "ingredient_master",
        "Inventory_History": "inventory_history",
        "Current_Stock": "current_stock"
    }
    if sheet_name not in table_map:
        raise HTTPException(status_code=400, detail="Invalid sheet name")
        
    table = table_map[sheet_name]
    with get_db() as conn:
        df = pd.read_sql_query(f"SELECT * FROM {table} WHERE restaurant_id = ?", conn, params=(restaurant_id,))
        
    if "restaurant_id" in df.columns:
        df = df.drop(columns=["restaurant_id"])
    return {"sheet_name": sheet_name, "columns": REQUIRED_COLUMNS[sheet_name], "rows": df.to_dict(orient="records")}

@app.post("/api/data/sheet/{sheet_name}/validate")
def validate_sheet(sheet_name: str, req: SheetSaveRequest, user: dict = Depends(get_current_user)):
    restaurant_id = user["restaurant_id"]
    with get_db() as conn:
        known_meals = set([r[0] for r in conn.execute("SELECT meal_id FROM meals WHERE restaurant_id = ?", (restaurant_id,)).fetchall()])
        known_ings = set([r[0] for r in conn.execute("SELECT ingredient FROM ingredient_master WHERE restaurant_id = ?", (restaurant_id,)).fetchall()])
    
    existing_data = {"known_meal_ids": known_meals, "known_ingredients": known_ings}
    errors = validate_sheet_data(sheet_name, req.rows, existing_data)
    return {"valid": len(errors) == 0, "errors": errors}

@app.post("/api/data/sheet/{sheet_name}/save")
def save_sheet(sheet_name: str, req: SheetSaveRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    restaurant_id = user["restaurant_id"]
    with get_db() as conn:
        known_meals = set([r[0] for r in conn.execute("SELECT meal_id FROM meals WHERE restaurant_id = ?", (restaurant_id,)).fetchall()])
        known_ings = set([r[0] for r in conn.execute("SELECT ingredient FROM ingredient_master WHERE restaurant_id = ?", (restaurant_id,)).fetchall()])
        
    errors = validate_sheet_data(sheet_name, req.rows, {"known_meal_ids": known_meals, "known_ingredients": known_ings})
    if errors:
        return {"status": "error", "message": "Validation failed", "errors": errors}
        
    table_map = {
        "Meals": "meals",
        "Daily_Orders": "daily_orders",
        "Next_7_Days_Inputs": "next_7_days_inputs",
        "Recipes": "recipes",
        "Ingredient_Master": "ingredient_master",
        "Inventory_History": "inventory_history",
        "Current_Stock": "current_stock"
    }
    table = table_map[sheet_name]
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table} WHERE restaurant_id = ?", (restaurant_id,))
        for r in req.rows:
            r_copy = r.copy()
            r_copy["restaurant_id"] = restaurant_id
            for d_col in ["date", "valid_from", "as_of_date", "earliest_expiry_date", "order_arrival_date"]:
                if d_col in r_copy:
                    r_copy[d_col] = parse_date_str(r_copy[d_col])
                    
            cols = list(r_copy.keys())
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
            cursor.execute(sql, [r_copy[c] for c in cols])
            
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE restaurants SET last_updated = ? WHERE id = ?", (now_str, restaurant_id))

    # Recalculate background
    background_tasks.add_task(trigger_full_recalculation, restaurant_id)
    return {"status": "success", "message": f"{sheet_name} saved successfully. Model recalculating in background."}

@app.post("/api/data/upload-file")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    filename = file.filename.lower()
    
    sheets_data = {}
    if filename.endswith(".xlsx"):
        excel_file = io.BytesIO(content)
        xls = pd.ExcelFile(excel_file)
        for s_name in xls.sheet_names:
            if s_name in REQUIRED_COLUMNS:
                df = pd.read_excel(xls, sheet_name=s_name)
                sheets_data[s_name] = df.to_dict(orient="records")
    elif filename.endswith(".csv"):
        # Match by filename or let user pick sheet
        matched_sheet = "Daily_Orders"
        for req_sheet in REQUIRED_COLUMNS:
            if req_sheet.lower() in filename:
                matched_sheet = req_sheet
                break
        df = pd.read_csv(io.BytesIO(content))
        sheets_data[matched_sheet] = df.to_dict(orient="records")
    else:
        raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are supported")
        
    return {"filename": file.filename, "sheets": sheets_data}

@app.post("/api/data/add-today")
def add_today_data(req: AddTodayRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    restaurant_id = user["restaurant_id"]
    target_date = parse_date_str(req.date)
    if not target_date:
        raise HTTPException(status_code=400, detail="Invalid target date format")
        
    dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
    day_of_week = dt.strftime("%A")
    
    with get_db() as conn:
        cursor = conn.cursor()
        meals_map = {r['meal_id']: dict(r) for r in conn.execute("SELECT * FROM meals WHERE restaurant_id = ?", (restaurant_id,)).fetchall()}
        
        # Insert orders
        for ord_row in req.orders:
            m_id = ord_row.get('meal_id')
            m_info = meals_map.get(m_id)
            if not m_info:
                continue
            cursor.execute("""
                INSERT OR REPLACE INTO daily_orders (
                    restaurant_id, date, day_of_week, meal_id, meal_name, category, cuisine,
                    checkout_price, base_price, promo_active, featured_on_menu, festival_or_event, num_orders
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                restaurant_id, target_date, day_of_week, m_id, m_info['meal_name'], m_info['category'], m_info['cuisine'],
                float(ord_row.get('checkout_price', m_info['base_price_inr'])), float(m_info['base_price_inr']),
                int(ord_row.get('promo_active', 0)), int(ord_row.get('featured_on_menu', 0)), int(ord_row.get('festival_or_event', 0)),
                int(ord_row.get('num_orders', 0))
            ))
            
        # Update current stock
        for stk_row in req.stocks:
            ing = stk_row.get('ingredient')
            cursor.execute("""
                INSERT OR REPLACE INTO current_stock (
                    restaurant_id, as_of_date, ingredient, unit, stock_on_hand,
                    earliest_expiry_date, qty_in_earliest_batch, order_in_transit_qty, order_arrival_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                restaurant_id, target_date, ing, stk_row.get('unit', 'kg'),
                float(stk_row.get('stock_on_hand', 0.0)),
                parse_date_str(stk_row.get('earliest_expiry_date')),
                float(stk_row.get('qty_in_earliest_batch', 0.0)),
                float(stk_row.get('order_in_transit_qty', 0.0)),
                parse_date_str(stk_row.get('order_arrival_date'))
            ))
            
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE restaurants SET last_updated = ? WHERE id = ?", (now_str, restaurant_id))

    # Advance the 7-day forecast horizon and retrain model
    background_tasks.add_task(trigger_full_recalculation, restaurant_id)
    return {"status": "success", "message": f"Data for {target_date} added successfully. Today moved forward and recalculation in progress."}

# --- Forecasting Endpoints ---
@app.get("/api/forecast/meals")
def get_meal_forecast(category: Optional[str] = None, cuisine: Optional[str] = None, user: dict = Depends(get_current_user)):
    df, categories, cuisines = get_meal_forecast_data(user["restaurant_id"], category, cuisine)
    dates = sorted(df['date'].unique().tolist()) if len(df) > 0 else []
    
    # Pivot meals x dates
    meals_matrix = {}
    for _, r in df.iterrows():
        m_id = r['meal_id']
        if m_id not in meals_matrix:
            meals_matrix[m_id] = {
                "meal_id": m_id,
                "meal_name": r['meal_name'],
                "category": r['category'],
                "cuisine": r['cuisine'],
                "base_price": r['base_price'],
                "days": {},
                "total_predicted_orders": 0.0
            }
        d = r['date']
        pred = r['predicted_orders'] or 0.0
        low = r['predicted_low'] or round(pred * 0.75, 1)
        high = r['predicted_high'] or round(pred * 1.25, 1)
        conf = r.get('confidence', 'high confidence')
        meals_matrix[m_id]["days"][d] = {
            "expected": round(pred, 1),
            "low": round(low, 1),
            "high": round(high, 1),
            "confidence": conf
        }
        meals_matrix[m_id]["total_predicted_orders"] += round(pred, 1)
        
    return {
        "dates": dates,
        "categories": categories,
        "cuisines": cuisines,
        "meals": list(meals_matrix.values())
    }

@app.get("/api/forecast/meal-history/{meal_id}")
def get_meal_history(meal_id: int, user: dict = Depends(get_current_user)):
    history, forecast = get_meal_history_and_forecast(user["restaurant_id"], meal_id)
    return {"history": history, "forecast": forecast}

@app.get("/api/model/status")
def get_model_status(user: dict = Depends(get_current_user)):
    restaurant_id = user["restaurant_id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM model_versions WHERE restaurant_id = ? AND is_active = 1", (restaurant_id,))
        row = cursor.fetchone()
        
        cursor.execute("SELECT version, trained_at, metrics_json, baselines_json FROM model_versions WHERE restaurant_id = ? ORDER BY id DESC LIMIT 5", (restaurant_id,))
        history_rows = cursor.fetchall()

    if not row:
        return {"status": "no_model", "message": "No trained model found. Click 'Retrain now' or load sample data."}

    history_versions = []
    for hr in history_rows:
        m_json = json.loads(hr['metrics_json'])
        history_versions.append({
            "version": hr['version'],
            "trained_at": hr['trained_at'],
            "wape": m_json.get('overall', {}).get('wape'),
            "mae": m_json.get('overall', {}).get('mae')
        })

    return {
        "status": "active",
        "version": row['version'],
        "trained_at": row['trained_at'],
        "metrics": json.loads(row['metrics_json']),
        "baselines": json.loads(row['baselines_json']),
        "feature_importances": json.loads(row['feature_importance_json']),
        "validation_chart": json.loads(row['validation_chart_json']),
        "history_versions": history_versions
    }

@app.post("/api/model/retrain")
def retrain_model(user: dict = Depends(get_current_user)):
    res = train_and_evaluate_model(user["restaurant_id"])
    return res

# --- Ingredient Forecast Endpoints ---
@app.get("/api/forecast/ingredients")
def get_ingredient_forecast_endpoint(user: dict = Depends(get_current_user)):
    return calculate_ingredient_forecast(user["restaurant_id"])

# --- Inventory & Orders Endpoints ---
@app.get("/api/inventory/status")
def get_inventory_status(user: dict = Depends(get_current_user)):
    return run_inventory_simulation(user["restaurant_id"])

@app.get("/api/orders/recommendations")
def get_orders_recommendations(user: dict = Depends(get_current_user)):
    sim = run_inventory_simulation(user["restaurant_id"])
    return {
        "orders_now": sim.get("orders_now", []),
        "orders_soon": sim.get("orders_soon", []),
        "summary": sim.get("summary", {})
    }

# --- Dashboard & Alerts Endpoints ---
@app.get("/api/dashboard")
def get_dashboard(user: dict = Depends(get_current_user)):
    return get_dashboard_data(user["restaurant_id"])

# --- Standout Features Endpoints ---
@app.post("/api/whatif/simulate")
def simulate_whatif(req: WhatIfSimulateRequest, user: dict = Depends(get_current_user)):
    return simulate_what_if_scenario(
        user["restaurant_id"], req.meal_id, req.date,
        req.checkout_price, req.promo_active, req.featured_on_menu, req.festival_or_event
    )

@app.post("/api/whatif/apply")
def apply_whatif(req: WhatIfApplyRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    res = apply_what_if_scenario(
        user["restaurant_id"], req.meal_id, req.date,
        req.checkout_price, req.promo_active, req.featured_on_menu, req.festival_or_event,
        req.simulated_orders
    )
    return res

@app.get("/api/whatif/use-first")
def use_it_first(user: dict = Depends(get_current_user)):
    return get_use_it_first_suggestions(user["restaurant_id"])

@app.get("/api/reports/savings")
def get_savings(user: dict = Depends(get_current_user)):
    return calculate_savings_report(user["restaurant_id"])

@app.get("/api/reports/purchase-orders/excel")
def download_po_excel(user: dict = Depends(get_current_user)):
    content = generate_purchase_orders_excel(user["restaurant_id"])
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=purchase_orders_{datetime.date.today()}.xlsx"}
    )

@app.get("/api/reports/purchase-orders/pdf")
def download_po_pdf(user: dict = Depends(get_current_user)):
    content = generate_purchase_orders_pdf(user["restaurant_id"])
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=purchase_orders_{datetime.date.today()}.pdf"}
    )

@app.post("/api/reports/export-table")
def export_table(req: ExportTableRequest):
    content = export_table_to_excel(req.table_name, req.rows, req.columns)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={req.table_name}.xlsx"}
    )

@app.get("/api/settings")
def get_settings(user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE restaurant_id = ?", (user["restaurant_id"],))
        row = cursor.fetchone()
        if not row:
            return {"email_alerts_enabled": False, "alert_email": user["email"], "notify_stockout": True, "notify_expiry": True, "notify_arrival": True}
        return dict(row)

@app.post("/api/settings")
def update_settings(req: SettingsRequest, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO settings (restaurant_id, email_alerts_enabled, alert_email, notify_stockout, notify_expiry, notify_arrival)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user["restaurant_id"], int(req.email_alerts_enabled), req.alert_email, int(req.notify_stockout), int(req.notify_expiry), int(req.notify_arrival)))
    return {"status": "success", "message": "Settings updated successfully"}

# Static files mount
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
