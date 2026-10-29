import pandas as pd
import numpy as np
from backend.database import get_db

INGREDIENT_CATEGORY_GROUPS = {
    # Proteins
    "Chicken": "Proteins", "Fish fillet": "Proteins", "Eggs": "Proteins", "Paneer": "Proteins",
    "Tofu": "Proteins", "Mutton": "Proteins", "Prawns": "Proteins", "Beef": "Proteins",
    # Vegetables
    "Tomato": "Vegetables", "Onion": "Vegetables", "Potato": "Vegetables", "Bell pepper": "Vegetables",
    "Spinach": "Vegetables", "Mushroom": "Vegetables", "Basil": "Vegetables", "Coriander": "Vegetables",
    "Garlic": "Vegetables", "Ginger": "Vegetables", "Carrot": "Vegetables", "Green peas": "Vegetables",
    "Cucumber": "Vegetables", "Lettuce": "Vegetables", "Cabbage": "Vegetables", "Broccoli": "Vegetables",
    "Green chili": "Vegetables", "Mint": "Vegetables", "Lemon": "Vegetables", "Spring onion": "Vegetables",
    # Dairy
    "Milk": "Dairy", "Butter": "Dairy", "Cheese": "Dairy", "Cream": "Dairy", "Yogurt": "Dairy",
    "Ghee": "Dairy", "Mozzarella": "Dairy", "Parmesan": "Dairy", "Cheddar": "Dairy", "Mayonnaise": "Dairy",
    # Grains
    "Basmati rice": "Grains", "Rice": "Grains", "Flour": "Grains", "Wheat flour": "Grains",
    "Noodles": "Grains", "Bread": "Grains", "Pasta": "Grains", "Rice noodles": "Grains",
    "Cornstarch": "Grains", "Oats": "Grains",
    # Pantry / Spices / Condiments / Beverages
    "Sugar": "Pantry", "Salt": "Pantry", "Cooking oil": "Pantry", "Oil": "Pantry", "Olive oil": "Pantry",
    "Chili powder": "Pantry", "Turmeric": "Pantry", "Cumin": "Pantry", "Garam masala": "Pantry",
    "Black pepper": "Pantry", "Soy sauce": "Pantry", "Vinegar": "Pantry", "Coffee beans": "Pantry",
    "Tea leaves": "Pantry", "Orange juice": "Pantry", "Tomato sauce": "Pantry", "Mustard": "Pantry",
    "Coriander seeds": "Pantry", "Cardamom": "Pantry", "Cinnamon": "Pantry", "Cloves": "Pantry"
}

def get_ingredient_group(ingredient_name: str) -> str:
    if ingredient_name in INGREDIENT_CATEGORY_GROUPS:
        return INGREDIENT_CATEGORY_GROUPS[ingredient_name]
    # Fallback heuristic
    lower = ingredient_name.lower()
    if any(k in lower for k in ["chicken", "fish", "egg", "meat", "mutton", "paneer", "tofu"]):
        return "Proteins"
    if any(k in lower for k in ["milk", "cream", "cheese", "butter", "curd", "yogurt", "ghee"]):
        return "Dairy"
    if any(k in lower for k in ["rice", "flour", "noodle", "bread", "pasta"]):
        return "Grains"
    if any(k in lower for k in ["onion", "tomato", "chili", "garlic", "ginger", "potato", "pepper", "spinach", "herb", "basil", "leaf"]):
        return "Vegetables"
    return "Pantry"

def calculate_ingredient_forecast(restaurant_id: str):
    """
    Computes daily ingredient demand for the next 7 days:
    For each day: sum over meals of orders x Recipes.qty_per_serving, per ingredient.
    Computes expected, low, and high.
    Returns:
    - daily_matrix: { ingredient: { unit, group, dates: { date: { expected, low, high } }, total_7d, total_cost } }
    - category_stacked_chart: [ { date, Proteins, Vegetables, Dairy, Grains, Pantry } ]
    - drill_down: { ingredient: [ { meal_id, meal_name, expected_orders_7d, qty_per_serving, total_qty_7d } ] }
    """
    with get_db() as conn:
        df_forecast = pd.read_sql_query("""
            SELECT date, meal_id, meal_name, predicted_orders, predicted_low, predicted_high
            FROM next_7_days_inputs
            WHERE restaurant_id = ?
            ORDER BY date, meal_id
        """, conn, params=(restaurant_id,))
        
        df_recipes = pd.read_sql_query("""
            SELECT meal_id, meal_name, ingredient, unit, qty_per_serving
            FROM recipes
            WHERE restaurant_id = ?
        """, conn, params=(restaurant_id,))
        
        df_master = pd.read_sql_query("""
            SELECT ingredient, unit, unit_cost_inr, shelf_life_days, supplier_lead_time_days
            FROM ingredient_master
            WHERE restaurant_id = ?
        """, conn, params=(restaurant_id,))

    if len(df_forecast) == 0 or len(df_recipes) == 0:
        return {"ingredients": [], "dates": [], "stacked_chart": [], "drill_down": {}}
        
    dates = sorted(df_forecast['date'].unique().tolist())
    
    # Merge recipes with forecast
    merged = pd.merge(df_recipes, df_forecast, on='meal_id', suffixes=('_rec', '_fc'))
    merged['expected_need'] = merged['predicted_orders'] * merged['qty_per_serving']
    merged['low_need'] = merged['predicted_low'] * merged['qty_per_serving']
    merged['high_need'] = merged['predicted_high'] * merged['qty_per_serving']
    
    master_map = df_master.set_index('ingredient').to_dict(orient='index')
    
    # Aggregate by (ingredient, date)
    daily_agg = merged.groupby(['ingredient', 'unit', 'date'])[['expected_need', 'low_need', 'high_need']].sum().reset_index()
    
    # Build complete ingredient map
    ingredient_dict = {}
    for ing in df_master['ingredient'].unique():
        m_info = master_map.get(ing, {})
        u = m_info.get('unit', '')
        group = get_ingredient_group(ing)
        unit_cost = m_info.get('unit_cost_inr', 0.0)
        ingredient_dict[ing] = {
            "ingredient": ing,
            "unit": u,
            "group": group,
            "unit_cost_inr": unit_cost,
            "days": {d: {"expected": 0.0, "low": 0.0, "high": 0.0} for d in dates},
            "total_7d": 0.0,
            "total_low_7d": 0.0,
            "total_high_7d": 0.0,
            "total_cost_7d": 0.0
        }
        
    for _, row in daily_agg.iterrows():
        ing = row['ingredient']
        d = row['date']
        if ing in ingredient_dict and d in ingredient_dict[ing]['days']:
            exp = round(float(row['expected_need']), 2)
            low = round(float(row['low_need']), 2)
            high = round(float(row['high_need']), 2)
            ingredient_dict[ing]['days'][d] = {"expected": exp, "low": low, "high": high}
            ingredient_dict[ing]['total_7d'] += exp
            ingredient_dict[ing]['total_low_7d'] += low
            ingredient_dict[ing]['total_high_7d'] += high

    for ing, data in ingredient_dict.items():
        data['total_7d'] = round(data['total_7d'], 2)
        data['total_low_7d'] = round(data['total_low_7d'], 2)
        data['total_high_7d'] = round(data['total_high_7d'], 2)
        data['total_cost_7d'] = round(data['total_7d'] * data['unit_cost_inr'], 2)
        
    # Stacked chart by group per day (sum of expected volume in standardized units or cost)
    stacked_chart = []
    for d in dates:
        entry = {"date": d, "Proteins": 0.0, "Vegetables": 0.0, "Dairy": 0.0, "Grains": 0.0, "Pantry": 0.0}
        for ing, data in ingredient_dict.items():
            grp = data['group']
            day_exp = data['days'][d]['expected']
            # We can use expenditure (kg/L weighted or cost in INR)
            cost_contrib = day_exp * data['unit_cost_inr']
            if grp in entry:
                entry[grp] += cost_contrib
        for g in ["Proteins", "Vegetables", "Dairy", "Grains", "Pantry"]:
            entry[g] = round(entry[g], 1)
        stacked_chart.append(entry)
        
    # Drill-down: which meals drive each ingredient
    drill_down = {}
    meal_drill = merged.groupby(['ingredient', 'meal_id', 'meal_name_rec', 'qty_per_serving'])[['predicted_orders', 'expected_need']].sum().reset_index()
    for _, row in meal_drill.iterrows():
        ing = row['ingredient']
        if ing not in drill_down:
            drill_down[ing] = []
        drill_down[ing].append({
            "meal_id": int(row['meal_id']),
            "meal_name": str(row['meal_name_rec']),
            "qty_per_serving": float(row['qty_per_serving']),
            "total_orders_7d": round(float(row['predicted_orders']), 1),
            "total_qty_7d": round(float(row['expected_need']), 2)
        })
        
    # Sort drill-down meals by highest demand
    for ing in drill_down:
        drill_down[ing].sort(key=lambda x: x['total_qty_7d'], reverse=True)
        
    ingredients_list = sorted(list(ingredient_dict.values()), key=lambda x: x['total_cost_7d'], reverse=True)
    return {
        "ingredients": ingredients_list,
        "dates": dates,
        "stacked_chart": stacked_chart,
        "drill_down": drill_down
    }
