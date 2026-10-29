import datetime
import math
import pandas as pd
import numpy as np
from backend.database import get_db
from backend.ingredients import calculate_ingredient_forecast, get_ingredient_group

def clean_val(val, default=None):
    if val is None or pd.isna(val):
        return default
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return default
    s = str(val).strip()
    if s.lower() in ('nan', 'none', '', 'null'):
        return default
    return val

def run_inventory_simulation(restaurant_id: str):
    """
    Simulates inventory over 7 forecast days using FIFO batch tracking.
    Assumptions:
    - Earliest batch expires on earliest_expiry_date.
    - Remaining stock expires on as_of_date + ceil(shelf_life_days / 2) (never earlier than earliest batch).
    - Orders in transit arrive on order_arrival_date and expire on arrival_date + shelf_life_days.
    - FIFO consumption draws from the earliest expiring batch.
    - All fields are strictly sanitized to prevent JSON NaN serialization errors.
    """
    forecast_data = calculate_ingredient_forecast(restaurant_id)
    ingredients_fc = {item['ingredient']: item for item in forecast_data.get('ingredients', [])}
    dates = forecast_data.get('dates', [])
    
    with get_db() as conn:
        df_stock = pd.read_sql_query("SELECT * FROM current_stock WHERE restaurant_id = ?", conn, params=(restaurant_id,))
        df_master = pd.read_sql_query("SELECT * FROM ingredient_master WHERE restaurant_id = ?", conn, params=(restaurant_id,))

    if len(df_stock) == 0:
        return {"inventory": [], "orders_now": [], "orders_soon": [], "summary": {}}

    stock_map = df_stock.set_index('ingredient').to_dict(orient='index')
    master_map = df_master.set_index('ingredient').to_dict(orient='index')
    
    inventory_results = []
    orders_now = []
    orders_soon = []
    
    total_waste_inr = 0.0
    items_at_risk_count = 0
    orders_due_today_count = 0

    for ing, stock_row in stock_map.items():
        m_info = master_map.get(ing, {})
        unit = str(clean_val(stock_row.get('unit'), m_info.get('unit', 'kg')) or 'kg')
        unit_cost = float(clean_val(m_info.get('unit_cost_inr'), 0.0) or 0.0)
        shelf_life = int(clean_val(m_info.get('shelf_life_days'), 7) or 7)
        lead_time = int(clean_val(m_info.get('supplier_lead_time_days'), 1) or 1)
        
        as_of_str = clean_val(stock_row.get('as_of_date'))
        as_of_dt = datetime.datetime.strptime(as_of_str, "%Y-%m-%d").date() if as_of_str else datetime.date(2026, 10, 29)
        
        stock_on_hand = float(clean_val(stock_row.get('stock_on_hand'), 0.0) or 0.0)
        earliest_exp_str = clean_val(stock_row.get('earliest_expiry_date'), None)
        qty_earliest = float(clean_val(stock_row.get('qty_in_earliest_batch'), 0.0) or 0.0)
        
        transit_qty = float(clean_val(stock_row.get('order_in_transit_qty'), 0.0) or 0.0)
        transit_date_str = clean_val(stock_row.get('order_arrival_date'), None)
        
        # Build initial batches
        batches = []
        if stock_on_hand > 0:
            b1_qty = min(qty_earliest, stock_on_hand) if qty_earliest > 0 else stock_on_hand
            try:
                b1_exp = datetime.datetime.strptime(earliest_exp_str, "%Y-%m-%d").date() if earliest_exp_str else (as_of_dt + datetime.timedelta(days=shelf_life))
            except Exception:
                b1_exp = as_of_dt + datetime.timedelta(days=shelf_life)
            batches.append({"qty": b1_qty, "expiry": b1_exp, "type": "initial_earliest"})
            
            rem_qty = stock_on_hand - b1_qty
            if rem_qty > 0.001:
                # Half shelf-life assumption, never earlier than earliest batch
                half_days = max(1, math.ceil(shelf_life / 2))
                b2_exp = max(as_of_dt + datetime.timedelta(days=half_days), b1_exp)
                batches.append({"qty": rem_qty, "expiry": b2_exp, "type": "initial_remaining"})

        # Daily tracking
        projected_stock_line = []
        stockout_date = None
        stockout_possible_date = None
        expired_qty_total = 0.0
        
        fc_entry = ingredients_fc.get(ing, {"days": {}, "total_7d": 0.0})
        fc_days = fc_entry.get("days", {})
        
        sim_batches = [dict(b) for b in batches]
        running_stock = stock_on_hand
        
        for d_str in dates:
            d_dt = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            
            # 1. In-transit arrival
            if transit_qty > 0 and transit_date_str == d_str:
                arrival_exp = d_dt + datetime.timedelta(days=shelf_life)
                sim_batches.append({"qty": transit_qty, "expiry": arrival_exp, "type": "in_transit"})
                running_stock += transit_qty

            # 2. Check expired batches before today's usage (expired before d_dt)
            valid_batches = []
            for b in sim_batches:
                if b["expiry"] < d_dt:
                    expired_qty_total += b["qty"]
                    running_stock -= b["qty"]
                else:
                    valid_batches.append(b)
            sim_batches = valid_batches

            # 3. Daily demand
            exp_need = fc_days.get(d_str, {}).get("expected", 0.0)
            high_need = fc_days.get(d_str, {}).get("high", 0.0)
            
            # Check stockout
            current_avail = sum(b["qty"] for b in sim_batches)
            if current_avail < exp_need and stockout_date is None:
                stockout_date = d_str
            elif current_avail < high_need and stockout_possible_date is None:
                stockout_possible_date = d_str

            # Deduct FIFO
            need_to_deduct = exp_need
            sim_batches.sort(key=lambda x: x["expiry"])
            for b in sim_batches:
                if need_to_deduct <= 0:
                    break
                deduct = min(b["qty"], need_to_deduct)
                b["qty"] -= deduct
                need_to_deduct -= deduct
                
            sim_batches = [b for b in sim_batches if b["qty"] > 0.001]
            running_stock = sum(b["qty"] for b in sim_batches)
            
            # Check batches expiring on day d_dt (end of day)
            end_valid = []
            for b in sim_batches:
                if b["expiry"] <= d_dt:
                    expired_qty_total += b["qty"]
                else:
                    end_valid.append(b)
            sim_batches = end_valid
            running_stock = sum(b["qty"] for b in sim_batches)
            
            projected_stock_line.append({"date": d_str, "stock": round(max(0.0, running_stock), 2)})

        total_need_7d = fc_entry.get("total_7d", 0.0)
        avg_daily_need = (total_need_7d / 7.0) if total_need_7d > 0 else 0.0
        if avg_daily_need > 0:
            days_of_cover = round(stock_on_hand / avg_daily_need, 1)
        else:
            days_of_cover = 99.0 if stock_on_hand > 0 else 0.0
            
        if math.isnan(days_of_cover) or math.isinf(days_of_cover):
            days_of_cover = 0.0
            
        # Status determination
        is_zero_critical = (stock_on_hand <= 0.001 and total_need_7d > 0)
        
        if is_zero_critical or stockout_date == dates[0] or (stockout_date is not None and (datetime.datetime.strptime(stockout_date, "%Y-%m-%d").date() - as_of_dt).days <= lead_time):
            status = "red"
            risk_label = "Stock-out risk"
        elif stockout_date is not None or expired_qty_total > 0.01:
            status = "red" if stockout_date else "amber"
            risk_label = "Stock-out risk" if stockout_date else "Expiry risk"
        elif stockout_possible_date is not None or days_of_cover < (lead_time + 2):
            status = "amber"
            risk_label = "Possible stock-out" if stockout_possible_date else "Low stock"
        else:
            status = "green"
            risk_label = "Safe"
            
        if status in ["red", "amber"]:
            items_at_risk_count += 1
            
        waste_inr = round(expired_qty_total * unit_cost, 2)
        total_waste_inr += waste_inr

        # Order suggestion logic
        needs_order = (status == "red") or (days_of_cover < (lead_time + 3) and total_need_7d > 0)
        
        order_suggestion = None
        if needs_order:
            if stockout_date:
                so_dt = datetime.datetime.strptime(stockout_date, "%Y-%m-%d").date()
                order_by_dt = so_dt - datetime.timedelta(days=lead_time)
            else:
                order_by_dt = as_of_dt

            is_late = (order_by_dt <= as_of_dt)
            order_by_final = as_of_dt if is_late else order_by_dt
            arrival_dt = order_by_final + datetime.timedelta(days=lead_time)
            
            coverage_window = max(1, min(shelf_life - 1, lead_time + 5))
            
            window_expected_need = 0.0
            window_safety_stock = 0.0
            for w in range(coverage_window):
                w_day = arrival_dt + datetime.timedelta(days=w)
                w_str = w_day.strftime("%Y-%m-%d")
                day_data = fc_days.get(w_str, {})
                exp_v = day_data.get("expected", avg_daily_need)
                high_v = day_data.get("high", avg_daily_need * 1.25)
                window_expected_need += exp_v
                window_safety_stock += max(0.0, high_v - exp_v)
                
            suggested_qty = math.ceil(max(0.0, window_expected_need + window_safety_stock - stock_on_hand - transit_qty))
            perishable_max = math.ceil(avg_daily_need * max(1, shelf_life - 1)) if shelf_life <= 7 else 999999.0
            suggested_qty = min(suggested_qty, perishable_max)
            suggested_qty = max(suggested_qty, 1.0 if total_need_7d > 0 else 0.0)
            
            order_cost = round(suggested_qty * unit_cost, 2)
            
            if is_late:
                reason = f"Urgent reorder required (Lead time {lead_time}d). Stock-out imminent."
            elif stockout_date:
                reason = f"Reorder to prevent stock-out on {stockout_date}."
            else:
                reason = f"Low stock: {days_of_cover} days of cover remaining."
                
            order_suggestion = {
                "ingredient": ing,
                "quantity": suggested_qty,
                "unit": unit,
                "unit_cost_inr": unit_cost,
                "order_by_date": order_by_final.strftime("%Y-%m-%d"),
                "arrival_date": arrival_dt.strftime("%Y-%m-%d"),
                "lead_time_days": lead_time,
                "shelf_life_days": shelf_life,
                "cost_inr": order_cost,
                "is_late": is_late,
                "reason": reason,
                "status": status
            }
            
            if is_late or order_by_final <= as_of_dt:
                orders_now.append(order_suggestion)
                orders_due_today_count += 1
            else:
                orders_soon.append(order_suggestion)

        inventory_results.append({
            "ingredient": ing,
            "unit": unit,
            "group": get_ingredient_group(ing),
            "stock_on_hand": stock_on_hand,
            "unit_cost_inr": unit_cost,
            "shelf_life_days": shelf_life,
            "supplier_lead_time_days": lead_time,
            "earliest_expiry_date": earliest_exp_str,
            "qty_in_earliest_batch": qty_earliest,
            "order_in_transit_qty": transit_qty,
            "order_arrival_date": transit_date_str,
            "days_of_cover": days_of_cover,
            "status": status,
            "risk_label": risk_label,
            "stockout_date": stockout_date,
            "stockout_possible_date": stockout_possible_date,
            "expired_qty_7d": round(expired_qty_total, 2),
            "waste_inr_7d": waste_inr,
            "projected_stock_line": projected_stock_line,
            "order_suggestion": order_suggestion
        })

    status_priority = {"red": 0, "amber": 1, "green": 2}
    inventory_results.sort(key=lambda x: (status_priority.get(x["status"], 2), x["days_of_cover"]))
    orders_now.sort(key=lambda x: x["cost_inr"], reverse=True)
    orders_soon.sort(key=lambda x: x["order_by_date"])

    return {
        "inventory": inventory_results,
        "orders_now": orders_now,
        "orders_soon": orders_soon,
        "summary": {
            "items_at_risk": items_at_risk_count,
            "orders_due_today": orders_due_today_count,
            "expected_waste_inr": round(total_waste_inr, 2),
            "total_inventory_items": len(inventory_results)
        }
    }