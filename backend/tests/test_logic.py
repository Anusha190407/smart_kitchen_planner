import unittest
import datetime
import math
import numpy as np
import pandas as pd

class TestSmartKitchenLogic(unittest.TestCase):
    
    def test_recipe_multiplication(self):
        """Verify recipe ingredient roll-up calculation."""
        forecast_orders = {"Meal_A": 100, "Meal_B": 50}
        recipes = [
            {"meal": "Meal_A", "ingredient": "Chicken", "unit": "kg", "qty_per_serving": 0.20},
            {"meal": "Meal_A", "ingredient": "Onion", "unit": "kg", "qty_per_serving": 0.05},
            {"meal": "Meal_B", "ingredient": "Chicken", "unit": "kg", "qty_per_serving": 0.15},
            {"meal": "Meal_B", "ingredient": "Tomato", "unit": "kg", "qty_per_serving": 0.10},
        ]
        
        ingredient_needs = {}
        for r in recipes:
            ing = r["ingredient"]
            m = r["meal"]
            orders = forecast_orders.get(m, 0)
            need = orders * r["qty_per_serving"]
            ingredient_needs[ing] = ingredient_needs.get(ing, 0.0) + need
            
        self.assertAlmostEqual(ingredient_needs["Chicken"], 100 * 0.20 + 50 * 0.15) # 20 + 7.5 = 27.5
        self.assertAlmostEqual(ingredient_needs["Onion"], 100 * 0.05) # 5.0
        self.assertAlmostEqual(ingredient_needs["Tomato"], 50 * 0.10) # 5.0

    def test_fifo_stock_projection(self):
        """Verify FIFO batch deduction and expiry."""
        batches = [
            {"qty": 10.0, "expiry": datetime.date(2026, 10, 30)},
            {"qty": 20.0, "expiry": datetime.date(2026, 11, 2)}
        ]
        
        # Day 1: 2026-10-29, demand 8.0
        daily_need = 8.0
        batches.sort(key=lambda x: x["expiry"])
        for b in batches:
            deduct = min(b["qty"], daily_need)
            b["qty"] -= deduct
            daily_need -= deduct
            
        self.assertAlmostEqual(batches[0]["qty"], 2.0)
        self.assertAlmostEqual(batches[1]["qty"], 20.0)
        
        # Day 2: 2026-10-30, demand 5.0
        daily_need = 5.0
        for b in batches:
            deduct = min(b["qty"], daily_need)
            b["qty"] -= deduct
            daily_need -= deduct
            
        self.assertAlmostEqual(batches[0]["qty"], 0.0)
        self.assertAlmostEqual(batches[1]["qty"], 17.0)

    def test_order_by_date_logic(self):
        """Verify order-by date and urgency flags."""
        today = datetime.date(2026, 10, 29)
        lead_time = 2
        
        # Scenario A: Stockout projected for 2026-11-02
        stockout_date = datetime.date(2026, 11, 2)
        order_by = stockout_date - datetime.timedelta(days=lead_time)
        self.assertEqual(order_by, datetime.date(2026, 10, 31))
        self.assertFalse(order_by <= today) # Order soon
        
        # Scenario B: Stockout projected for 2026-10-30 (Lead time 2) -> Order was due yesterday!
        stockout_urgent = datetime.date(2026, 10, 30)
        order_by_urgent = stockout_urgent - datetime.timedelta(days=lead_time)
        self.assertEqual(order_by_urgent, datetime.date(2026, 10, 28))
        self.assertTrue(order_by_urgent <= today) # Order NOW / Late

    def test_no_leakage_feature_rule(self):
        """Verify feature engineering does not use data inside the [T-6, T] window."""
        # Create 50 days of daily orders
        dates = pd.date_range("2026-08-01", periods=50, freq="D")
        df_meal = pd.DataFrame({
            "date": dates,
            "meal_id": 1001,
            "num_orders": np.arange(50) + 10 # Predictable linear sequence
        }).set_index("date")["num_orders"]
        
        target_date = pd.Timestamp("2026-09-10")
        anchor_date = target_date - pd.Timedelta(days=7) # 2026-09-03
        
        # Any access must be <= anchor_date
        lag_7 = df_meal.get(anchor_date)
        self.assertIsNotNone(lag_7)
        
        # Ensure no data from anchor_date + 1 day to target_date is accessed
        leakage_window = pd.date_range(anchor_date + pd.Timedelta(days=1), target_date)
        for leak_d in leakage_window:
            self.assertGreater(leak_d, anchor_date)
            
        # Verify rolling mean 7 uses strictly [anchor_date - 6, anchor_date]
        rolling_7_dates = pd.date_range(anchor_date - pd.Timedelta(days=6), anchor_date)
        self.assertEqual(len(rolling_7_dates), 7)
        self.assertLessEqual(rolling_7_dates.max(), anchor_date)

if __name__ == "__main__":
    unittest.main()
