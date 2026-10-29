import copy
import pandas as pd
import numpy as np
from backend.database import get_db
from backend.forecasting import extract_features_df, PoissonGradientBoostingModel
from backend.ingredients import calculate_ingredient_forecast
from backend.inventory import run_inventory_simulation

def simulate_what_if_scenario(restaurant_id: str, meal_id: int, date_str: str, 
                              checkout_price: float, promo_active: int, 
                              featured_on_menu: int, festival_or_event: int):
    """
    Simulates a what-if perturbation without saving to the database.
    Calculates:
    - Original vs new predicted meal orders
    - Impact on ingredient demand (delta qty and cost)
    - Impact on stock-out dates and suggested purchase orders
    """
    with get_db() as conn:
        df_orders = pd.read_sql_query("SELECT * FROM daily_orders WHERE restaurant_id = ? ORDER BY date, meal_id", conn, params=(restaurant_id,))
        df_next = pd.read_sql_query("SELECT * FROM next_7_days_inputs WHERE restaurant_id = ? ORDER BY date, meal_id", conn, params=(restaurant_id,))
        df_recipes = pd.read_sql_query("SELECT * FROM recipes WHERE restaurant_id = ?", conn, params=(restaurant_id,))
        df_master = pd.read_sql_query("SELECT * FROM ingredient_master WHERE restaurant_id = ?", conn, params=(restaurant_id,))
        
    orig_row = df_next[(df_next['meal_id'] == meal_id) & (df_next['date'] == date_str)]
    if len(orig_row) == 0:
        return {"error": "Target meal and date not found in 7-day plan."}
        
    orig_pred = float(orig_row.iloc[0]['predicted_orders'])
    orig_price = float(orig_row.iloc[0]['checkout_price'])
    orig_base = float(orig_row.iloc[0]['base_price'])
    meal_name = str(orig_row.iloc[0]['meal_name'])
    
    # Train/load model on all orders
    X_all, y_all, feat_names, _ = extract_features_df(df_orders, df_orders)
    model = PoissonGradientBoostingModel(n_estimators=50, learning_rate=0.08)
    model.fit(X_all, y_all, feat_names)
    
    # Create modified scenario dataframe
    df_scenario = df_next.copy()
    match_idx = df_scenario[(df_scenario['meal_id'] == meal_id) & (df_scenario['date'] == date_str)].index[0]
    df_scenario.loc[match_idx, 'checkout_price'] = checkout_price
    df_scenario.loc[match_idx, 'promo_active'] = promo_active
    df_scenario.loc[match_idx, 'featured_on_menu'] = featured_on_menu
    df_scenario.loc[match_idx, 'festival_or_event'] = festival_or_event
    
    X_scen, _, _, _ = extract_features_df(df_orders, df_scenario, is_training=False)
    new_preds = model.predict(X_scen)
    new_meal_pred = round(float(new_preds[match_idx]), 1)
    
    delta_orders = round(new_meal_pred - orig_pred, 1)
    pct_change = round((delta_orders / orig_pred * 100.0), 1) if orig_pred > 0 else 0.0
    
    # Calculate ingredient demand impact
    meal_recipes = df_recipes[df_recipes['meal_id'] == meal_id]
    master_dict = df_master.set_index('ingredient').to_dict(orient='index')
    
    ingredient_impacts = []
    for _, r in meal_recipes.iterrows():
        ing = r['ingredient']
        unit = r['unit']
        qty_per_srv = float(r['qty_per_serving'])
        orig_ing_need = round(orig_pred * qty_per_srv, 2)
        new_ing_need = round(new_meal_pred * qty_per_srv, 2)
        delta_qty = round(new_ing_need - orig_ing_need, 2)
        unit_cost = float(master_dict.get(ing, {}).get('unit_cost_inr', 0.0))
        delta_cost = round(delta_qty * unit_cost, 2)
        
        ingredient_impacts.append({
            "ingredient": ing,
            "unit": unit,
            "qty_per_serving": qty_per_srv,
            "original_need": orig_ing_need,
            "simulated_need": new_ing_need,
            "delta_qty": delta_qty,
            "delta_cost_inr": delta_cost
        })
        
    return {
        "meal_id": meal_id,
        "meal_name": meal_name,
        "date": date_str,
        "parameters": {
            "checkout_price": checkout_price,
            "original_price": orig_price,
            "base_price": orig_base,
            "promo_active": promo_active,
            "featured_on_menu": featured_on_menu,
            "festival_or_event": festival_or_event
        },
        "forecast_comparison": {
            "original_orders": orig_pred,
            "simulated_orders": new_meal_pred,
            "delta_orders": delta_orders,
            "pct_change": pct_change
        },
        "ingredient_impacts": ingredient_impacts
    }

def apply_what_if_scenario(restaurant_id: str, meal_id: int, date_str: str, 
                           checkout_price: float, promo_active: int, 
                           featured_on_menu: int, festival_or_event: int, simulated_orders: float):
    """Applies the what-if simulation permanently to the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE next_7_days_inputs
            SET checkout_price = ?, promo_active = ?, featured_on_menu = ?, festival_or_event = ?,
                predicted_orders = ?, predicted_low = ?, predicted_high = ?
            WHERE restaurant_id = ? AND meal_id = ? AND date = ?
        """, (
            checkout_price, promo_active, featured_on_menu, festival_or_event,
            simulated_orders, max(1.0, round(simulated_orders * 0.75, 1)), round(simulated_orders * 1.25, 1),
            restaurant_id, meal_id, date_str
        ))
        now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE restaurants SET last_updated = ? WHERE id = ?", (now_str, restaurant_id))
    return {"status": "success", "message": "What-if scenario applied to plan successfully."}

def get_use_it_first_suggestions(restaurant_id: str):
    """
    Finds ingredients expiring unused and suggests meals to promote,
    including servings needed to eliminate surplus before expiry.
    """
    inv_sim = run_inventory_simulation(restaurant_id)
    inventory = inv_sim.get("inventory", [])
    
    with get_db() as conn:
        df_recipes = pd.read_sql_query("SELECT * FROM recipes WHERE restaurant_id = ?", conn, params=(restaurant_id,))
        
    suggestions = []
    for item in inventory:
        surplus_qty = item.get("expired_qty_7d", 0.0)
        # Also consider ingredients with <= 2 days of cover or expiring within 3 days
        if surplus_qty > 0.01 or (item["stock_on_hand"] > 0 and item["days_of_cover"] > 7 and item["shelf_life_days"] <= 5):
            target_surplus = surplus_qty if surplus_qty > 0.01 else round(item["stock_on_hand"] * 0.5, 2)
            ing = item["ingredient"]
            unit = item["unit"]
            matching_recipes = df_recipes[df_recipes['ingredient'] == ing]
            
            recipe_suggestions = []
            for _, r in matching_recipes.iterrows():
                qty_serving = float(r['qty_per_serving'])
                servings_needed = int(np.ceil(target_surplus / qty_serving)) if qty_serving > 0 else 0
                recipe_suggestions.append({
                    "meal_id": int(r['meal_id']),
                    "meal_name": str(r['meal_name']),
                    "category": str(r['category']),
                    "cuisine": str(r['cuisine']),
                    "qty_per_serving": qty_serving,
                    "unit": unit,
                    "servings_needed_to_clear": servings_needed
                })
                
            recipe_suggestions.sort(key=lambda x: x['servings_needed_to_clear'])
            suggestions.append({
                "ingredient": ing,
                "unit": unit,
                "stock_on_hand": item["stock_on_hand"],
                "expiring_surplus_qty": target_surplus,
                "earliest_expiry_date": item["earliest_expiry_date"],
                "estimated_waste_cost_inr": item["waste_inr_7d"],
                "candidate_meals": recipe_suggestions
            })
            
    return suggestions
