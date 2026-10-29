import datetime
import pandas as pd
from backend.database import get_db
from backend.inventory import run_inventory_simulation

def get_dashboard_data(restaurant_id: str):
    """
    Computes dashboard KPIs:
    1. Items at risk
    2. Orders due today
    3. Expected waste (INR)
    4. Forecast accuracy (WAPE / Accuracy %)
    And components:
    - 7-day total orders chart
    - 'Order now' list
    - 'Use first' list (closest to expiry)
    - Alerts list sorted by urgency
    """
    inv_sim = run_inventory_simulation(restaurant_id)
    summary = inv_sim.get("summary", {})
    orders_now = inv_sim.get("orders_now", [])
    inventory = inv_sim.get("inventory", [])
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Forecast accuracy from active model
        cursor.execute("SELECT metrics_json FROM model_versions WHERE restaurant_id = ? AND is_active = 1", (restaurant_id,))
        m_row = cursor.fetchone()
        forecast_accuracy = "N/A"
        wape_val = None
        if m_row and m_row['metrics_json']:
            import json
            m_dict = json.loads(m_row['metrics_json'])
            wape = m_dict.get('overall', {}).get('wape')
            if wape is not None:
                wape_val = wape
                # Accuracy display: 100 - WAPE or WAPE
                acc = max(0.0, round(100.0 - float(wape), 1))
                forecast_accuracy = f"{acc}% (WAPE: {wape}%)"
                
        # 2. 7-day total orders chart
        cursor.execute("""
            SELECT date, day_of_week, SUM(predicted_orders) as total_orders
            FROM next_7_days_inputs
            WHERE restaurant_id = ?
            GROUP BY date, day_of_week
            ORDER BY date
        """, (restaurant_id,))
        orders_chart = [dict(r) for r in cursor.fetchall()]

    # 3. Use first list: ingredients closest to expiry with stock > 0
    use_first_items = []
    for item in inventory:
        if item["stock_on_hand"] > 0 and item["earliest_expiry_date"]:
            use_first_items.append({
                "ingredient": item["ingredient"],
                "unit": item["unit"],
                "stock_on_hand": item["stock_on_hand"],
                "earliest_expiry_date": item["earliest_expiry_date"],
                "qty_in_earliest_batch": item["qty_in_earliest_batch"],
                "days_of_cover": item["days_of_cover"],
                "waste_inr_7d": item["waste_inr_7d"],
                "status": item["status"]
            })
    use_first_items.sort(key=lambda x: (x["earliest_expiry_date"], -x["waste_inr_7d"]))
    use_first_items = use_first_items[:8]

    # 4. Alerts sorted by urgency:
    # 0: Critical stock-out today / imminent
    # 1: Major expiry risk
    # 2: Supplier order arriving today
    # 3: Low stock warning
    alerts = []
    today_str = inv_sim.get("inventory", [{}])[0].get("order_arrival_date") # Or as_of_date
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT as_of_date FROM current_stock WHERE restaurant_id = ? LIMIT 1", (restaurant_id,))
        as_of_row = cursor.fetchone()
        today_date = as_of_row['as_of_date'] if as_of_row else "2026-10-29"

    for item in inventory:
        # Stock-out alert
        if item["status"] == "red" and item["stockout_date"]:
            urgency = 0 if item["stockout_date"] == today_date else 1
            alerts.append({
                "type": "stockout",
                "urgency": urgency,
                "severity": "red",
                "title": f"Stock-out Risk: {item['ingredient']}",
                "message": f"Projected to run out of stock on {item['stockout_date']}. Immediate replenishment required.",
                "ingredient": item["ingredient"]
            })
        elif item["stock_on_hand"] <= 0.001 and item.get("order_suggestion"):
            alerts.append({
                "type": "stockout",
                "urgency": 0,
                "severity": "red",
                "title": f"Zero Stock: {item['ingredient']}",
                "message": f"Zero stock on hand. Order needed today to prevent menu disruption.",
                "ingredient": item["ingredient"]
            })

        # Expiry alert
        if item["expired_qty_7d"] > 0:
            alerts.append({
                "type": "expiry",
                "urgency": 2,
                "severity": "amber",
                "title": f"Expiry Risk: {item['ingredient']}",
                "message": f"{item['expired_qty_7d']} {item['unit']} will expire unused (Est. waste: ₹{item['waste_inr_7d']:,}).",
                "ingredient": item["ingredient"]
            })

        # Supplier arrival alert
        if item["order_in_transit_qty"] > 0 and item["order_arrival_date"] == today_date:
            alerts.append({
                "type": "arrival",
                "urgency": 3,
                "severity": "green",
                "title": f"Order Arriving Today: {item['ingredient']}",
                "message": f"Scheduled delivery of {item['order_in_transit_qty']} {item['unit']} arriving today.",
                "ingredient": item["ingredient"]
            })

    alerts.sort(key=lambda x: x["urgency"])

    return {
        "kpis": {
            "items_at_risk": summary.get("items_at_risk", 0),
            "orders_due_today": summary.get("orders_due_today", 0),
            "expected_waste_inr": summary.get("expected_waste_inr", 0.0),
            "forecast_accuracy": forecast_accuracy,
            "wape": wape_val
        },
        "orders_chart": orders_chart,
        "orders_now": orders_now,
        "use_first": use_first_items,
        "alerts": alerts
    }
