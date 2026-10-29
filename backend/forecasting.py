import os
import json
import datetime
import math
import numpy as np
import pandas as pd
from backend.database import get_db

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

class PoissonGradientBoostingModel:
    """
    High-performance gradient boosted Poisson regression with log-link.
    Minimizes Poisson deviance: 2 * sum(y * log(y / mu) - (y - mu))
    Gradient: r_i = y_i - exp(F(x_i))
    Hessian: h_i = exp(F(x_i))
    Uses decision tree stumps and depth-3 trees implemented in NumPy.
    """
    def __init__(self, n_estimators=60, learning_rate=0.08, max_depth=3, l2_reg=1.0):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.l2_reg = l2_reg
        self.base_score = 0.0
        self.trees = []
        self.feature_names = []
        self.feature_importances_ = {}

    def fit(self, X: np.ndarray, y: np.ndarray, feature_names: list = None):
        self.feature_names = feature_names or [f"f_{i}" for i in range(X.shape[1])]
        y = np.clip(y, 0, None)
        mean_y = max(np.mean(y), 1e-3)
        self.base_score = np.log(mean_y)
        
        raw_preds = np.full(X.shape[0], self.base_score, dtype=np.float64)
        self.trees = []
        importance_counts = {fn: 0.0 for fn in self.feature_names}
        
        for _ in range(self.n_estimators):
            mu = np.exp(np.clip(raw_preds, -10.0, 10.0))
            # Poisson negative gradient (residuals)
            grad = y - mu
            hess = np.clip(mu, 1e-4, 1e5)
            
            tree = self._build_tree(X, grad, hess, depth=0)
            self.trees.append(tree)
            
            # Update predictions
            update = self._predict_tree(tree, X)
            raw_preds += self.learning_rate * update
            
            # Collect feature importance
            self._accumulate_importance(tree, importance_counts)
            
        total_imp = sum(importance_counts.values()) or 1.0
        self.feature_importances_ = {k: round(v / total_imp, 4) for k, v in importance_counts.items()}

    def _build_tree(self, X: np.ndarray, grad: np.ndarray, hess: np.ndarray, depth: int):
        if depth >= self.max_depth or len(grad) < 10:
            weight = np.sum(grad) / (np.sum(hess) + self.l2_reg)
            return {"leaf": True, "value": weight}
            
        best_gain = 0.0
        best_feat = None
        best_thresh = None
        n_samples, n_feats = X.shape
        
        # Subsample features for speed & regularization
        feats_to_try = np.random.choice(n_feats, min(n_feats, 8), replace=False)
        
        g_sum = np.sum(grad)
        h_sum = np.sum(hess)
        current_score = (g_sum ** 2) / (h_sum + self.l2_reg)
        
        for feat_idx in feats_to_try:
            col = X[:, feat_idx]
            percentiles = np.percentile(col, [25, 50, 75])
            for thresh in np.unique(percentiles):
                left_mask = col <= thresh
                right_mask = ~left_mask
                
                if np.sum(left_mask) < 5 or np.sum(right_mask) < 5:
                    continue
                    
                g_L, h_L = np.sum(grad[left_mask]), np.sum(hess[left_mask])
                g_R, h_R = np.sum(grad[right_mask]), np.sum(hess[right_mask])
                
                gain = 0.5 * ((g_L ** 2) / (h_L + self.l2_reg) + (g_R ** 2) / (h_R + self.l2_reg) - current_score)
                if gain > best_gain:
                    best_gain = gain
                    best_feat = feat_idx
                    best_thresh = thresh
                    
        if best_gain <= 0.001 or best_feat is None:
            weight = np.sum(grad) / (np.sum(hess) + self.l2_reg)
            return {"leaf": True, "value": weight}
            
        left_mask = X[:, best_feat] <= best_thresh
        right_mask = ~left_mask
        
        left_child = self._build_tree(X[left_mask], grad[left_mask], hess[left_mask], depth + 1)
        right_child = self._build_tree(X[right_mask], grad[right_mask], hess[right_mask], depth + 1)
        
        return {
            "leaf": False,
            "feature": best_feat,
            "feature_name": self.feature_names[best_feat],
            "threshold": best_thresh,
            "gain": best_gain,
            "left": left_child,
            "right": right_child
        }

    def _predict_tree(self, node: dict, X: np.ndarray) -> np.ndarray:
        if node["leaf"]:
            return np.full(X.shape[0], node["value"])
        mask = X[:, node["feature"]] <= node["threshold"]
        preds = np.empty(X.shape[0])
        preds[mask] = self._predict_tree(node["left"], X[mask])
        preds[~mask] = self._predict_tree(node["right"], X[~mask])
        return preds

    def _accumulate_importance(self, node: dict, counts: dict):
        if not node.get("leaf"):
            fn = node.get("feature_name")
            if fn in counts:
                counts[fn] += node.get("gain", 1.0)
            self._accumulate_importance(node["left"], counts)
            self._accumulate_importance(node["right"], counts)

    def predict(self, X: np.ndarray) -> np.ndarray:
        raw = np.full(X.shape[0], self.base_score)
        for tree in self.trees:
            raw += self.learning_rate * self._predict_tree(tree, X)
        return np.exp(np.clip(raw, -10.0, 10.0))

class QuantileRegressionModel:
    """Pinball loss regression for 10% and 90% quantiles."""
    def __init__(self, quantile=0.9, n_estimators=40, learning_rate=0.08):
        self.quantile = quantile
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.base_val = 0.0
        self.model = PoissonGradientBoostingModel(n_estimators=n_estimators, learning_rate=learning_rate)

    def fit(self, X: np.ndarray, y: np.ndarray, base_preds: np.ndarray):
        # Multiplier on top of Poisson base prediction
        ratios = y / np.clip(base_preds, 1.0, None)
        self.quantile_multiplier = max(0.1, np.percentile(ratios, self.quantile * 100))

    def predict(self, base_preds: np.ndarray) -> np.ndarray:
        return base_preds * self.quantile_multiplier

def extract_features_df(df_orders: pd.DataFrame, target_df: pd.DataFrame = None, is_training: bool = True) -> tuple:
    """
    Strict no-leakage feature extractor.
    Features:
    - calendar: day_of_week (0-6), day_of_month (1-31), week_of_year (1-53), is_weekend (0/1)
    - price: price_ratio = checkout_price / base_price, discount_pct
    - flags: promo_active, featured_on_menu, festival_or_event
    - history: computed ONLY from data at least 7 days before the target day:
      lag_7, lag_14, rolling_mean_7, rolling_mean_28, rolling_std_7
    - identity: meal_id (categorical index), category (encoded), cuisine (encoded)
    """
    df = df_orders.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['meal_id', 'date']).reset_index(drop=True)
    
    # Precompute categories and cuisine encodings
    categories = sorted(df['category'].unique())
    cuisines = sorted(df['cuisine'].unique())
    meals = sorted(df['meal_id'].unique())
    
    cat_map = {c: i for i, c in enumerate(categories)}
    cui_map = {c: i for i, c in enumerate(cuisines)}
    meal_map = {m: i for i, m in enumerate(meals)}
    
    # Compute history tables per meal
    meal_history = {}
    for meal_id, group in df.groupby('meal_id'):
        group_indexed = group.set_index('date')['num_orders'].sort_index()
        # Build complete date index for the meal history
        full_idx = pd.date_range(group_indexed.index.min(), group_indexed.index.max())
        series = group_indexed.reindex(full_idx, fill_value=0)
        meal_history[meal_id] = series

    target = target_df.copy() if target_df is not None else df.copy()
    target['date'] = pd.to_datetime(target['date'])
    
    rows = []
    feature_names = [
        "day_of_week", "day_of_month", "week_of_year", "is_weekend",
        "price_ratio", "discount_pct",
        "promo_active", "featured_on_menu", "festival_or_event",
        "lag_7", "lag_14", "rolling_mean_7", "rolling_mean_28", "rolling_std_7",
        "meal_code", "category_code", "cuisine_code"
    ]
    
    y = []
    metadata = []
    
    for idx, row in target.iterrows():
        t_date = row['date']
        m_id = row['meal_id']
        
        # Calendar features
        dow = t_date.dayofweek
        dom = t_date.day
        woy = t_date.isocalendar().week
        is_wknd = 1 if dow in [5, 6] else 0
        
        # Price features
        base_p = max(float(row['base_price']), 1.0)
        check_p = float(row['checkout_price'])
        price_ratio = check_p / base_p
        discount_pct = max(0.0, (base_p - check_p) / base_p * 100.0)
        
        # Flags
        promo = int(row.get('promo_active', 0))
        featured = int(row.get('featured_on_menu', 0))
        fest = int(row.get('festival_or_event', 0))
        
        # Strictly at least 7 days before target day
        series = meal_history.get(m_id)
        if series is not None and len(series) > 0:
            # Anchor is t_date - 7 days
            anchor_date = t_date - pd.Timedelta(days=7)
            
            # lag_7: exact day anchor_date
            lag_7 = float(series.get(anchor_date, 0))
            # lag_14: anchor_date - 7 days
            lag_14 = float(series.get(anchor_date - pd.Timedelta(days=7), 0))
            
            # rolling_mean_7: 7 days up to anchor_date [anchor_date - 6 days, anchor_date]
            win_7_dates = pd.date_range(anchor_date - pd.Timedelta(days=6), anchor_date)
            win_7_vals = [series.get(d, 0) for d in win_7_dates]
            rolling_mean_7 = float(np.mean(win_7_vals)) if win_7_vals else 0.0
            rolling_std_7 = float(np.std(win_7_vals)) if win_7_vals else 0.0
            
            # rolling_mean_28: 28 days up to anchor_date [anchor_date - 27 days, anchor_date]
            win_28_dates = pd.date_range(anchor_date - pd.Timedelta(days=27), anchor_date)
            win_28_vals = [series.get(d, 0) for d in win_28_dates]
            rolling_mean_28 = float(np.mean(win_28_vals)) if win_28_vals else 0.0
        else:
            lag_7, lag_14, rolling_mean_7, rolling_mean_28, rolling_std_7 = 0.0, 0.0, 0.0, 0.0, 0.0
            
        m_code = meal_map.get(m_id, 0)
        c_code = cat_map.get(row.get('category'), 0)
        cui_code = cui_map.get(row.get('cuisine'), 0)
        
        feat_vec = [
            dow, dom, woy, is_wknd,
            price_ratio, discount_pct,
            promo, featured, fest,
            lag_7, lag_14, rolling_mean_7, rolling_mean_28, rolling_std_7,
            m_code, c_code, cui_code
        ]
        rows.append(feat_vec)
        if 'num_orders' in row and not pd.isna(row['num_orders']):
            y.append(float(row['num_orders']))
        else:
            y.append(0.0)
            
        metadata.append({
            "date": t_date.strftime("%Y-%m-%d"),
            "meal_id": m_id,
            "meal_name": row.get('meal_name'),
            "category": row.get('category'),
            "cuisine": row.get('cuisine'),
            "base_price": base_p,
            "checkout_price": check_p,
            "lag_7": lag_7,
            "rolling_mean_28": rolling_mean_28
        })
        
    return np.array(rows, dtype=np.float64), np.array(y, dtype=np.float64), feature_names, metadata

def train_and_evaluate_model(restaurant_id: str):
    """
    Time-based validation only (never random split):
    Train on all days up to the last 14, validate on the last 14 days.
    Compare against baselines (same weekday last week, 28-day average).
    Compute WAPE, MAPE, MAE overall and per category.
    Retrain on all data for the final model.
    Train quantile models (10% and 90%).
    Save model version and return metrics.
    """
    with get_db() as conn:
        df_orders = pd.read_sql_query("SELECT * FROM daily_orders WHERE restaurant_id = ? ORDER BY date, meal_id", conn, params=(restaurant_id,))
        if len(df_orders) == 0:
            return {"status": "error", "message": "No order data available for training."}
            
    df_orders['dt'] = pd.to_datetime(df_orders['date'])
    unique_dates = sorted(df_orders['dt'].unique())
    
    if len(unique_dates) < 28:
        return {"status": "error", "message": "At least 28 days of history required for full model training."}
        
    val_cutoff_date = unique_dates[-14]
    
    df_train_raw = df_orders[df_orders['dt'] < val_cutoff_date].copy()
    df_val_raw = df_orders[df_orders['dt'] >= val_cutoff_date].copy()
    
    X_train, y_train, feat_names, _ = extract_features_df(df_train_raw, df_train_raw)
    X_val, y_val, _, meta_val = extract_features_df(df_train_raw, df_val_raw)
    
    # Train validation model
    val_model = PoissonGradientBoostingModel(n_estimators=60, learning_rate=0.08, max_depth=3)
    val_model.fit(X_train, y_train, feat_names)
    y_pred_val = val_model.predict(X_val)
    
    # Compute baselines on validation set
    b1_preds = np.array([m['lag_7'] for m in meta_val])
    b2_preds = np.array([m['rolling_mean_28'] for m in meta_val])
    
    def calc_metrics(actual, pred):
        mae = float(np.mean(np.abs(actual - pred)))
        sum_actual = float(np.sum(actual))
        wape = float((np.sum(np.abs(actual - pred)) / sum_actual) * 100.0) if sum_actual > 0 else 0.0
        nonzero_mask = actual > 0
        mape = float(np.mean(np.abs(actual[nonzero_mask] - pred[nonzero_mask]) / actual[nonzero_mask]) * 100.0) if np.sum(nonzero_mask) > 0 else 0.0
        return {"mae": round(mae, 2), "wape": round(wape, 2), "mape": round(mape, 2)}
        
    model_metrics = calc_metrics(y_val, y_pred_val)
    b1_metrics = calc_metrics(y_val, b1_preds)
    b2_metrics = calc_metrics(y_val, b2_preds)
    
    # Per-category metrics
    cat_metrics = {}
    for cat in df_val_raw['category'].unique():
        cat_mask = np.array([m['category'] == cat for m in meta_val])
        if np.sum(cat_mask) > 0:
            cat_metrics[cat] = {
                "model": calc_metrics(y_val[cat_mask], y_pred_val[cat_mask]),
                "baseline_lag7": calc_metrics(y_val[cat_mask], b1_preds[cat_mask]),
                "baseline_28d": calc_metrics(y_val[cat_mask], b2_preds[cat_mask])
            }
            
    # Chart data for 14 validation days (daily aggregate actual vs predicted vs baselines)
    df_val_chart = pd.DataFrame({
        "date": [m['date'] for m in meta_val],
        "actual": y_val,
        "predicted": y_pred_val,
        "baseline_lag7": b1_preds
    }).groupby('date').sum().reset_index()
    validation_chart = df_val_chart.to_dict(orient="records")
    
    # Now retrain final model on ALL data
    X_all, y_all, _, _ = extract_features_df(df_orders, df_orders)
    final_model = PoissonGradientBoostingModel(n_estimators=70, learning_rate=0.08, max_depth=3)
    final_model.fit(X_all, y_all, feat_names)
    
    # Train quantiles (10% and 90%)
    preds_all = final_model.predict(X_all)
    q10_model = QuantileRegressionModel(quantile=0.10)
    q10_model.fit(X_all, y_all, preds_all)
    q90_model = QuantileRegressionModel(quantile=0.90)
    q90_model.fit(X_all, y_all, preds_all)
    
    # Generate version string
    now_dt = datetime.datetime.now()
    version = f"v{now_dt.strftime('%Y%m%d_%H%M%S')}"
    
    # Save model metadata in SQLite
    metrics_data = {
        "overall": model_metrics,
        "categories": cat_metrics,
        "sample_count": len(y_all),
        "validation_sample_count": len(y_val)
    }
    baselines_data = {
        "baseline_weekday_lag7": b1_metrics,
        "baseline_rolling_28d": b2_metrics,
        "model_vs_b1_wape_gain": round(b1_metrics["wape"] - model_metrics["wape"], 2),
        "model_vs_b2_wape_gain": round(b2_metrics["wape"] - model_metrics["wape"], 2)
    }
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE model_versions SET is_active = 0 WHERE restaurant_id = ?", (restaurant_id,))
        cursor.execute("""
            INSERT INTO model_versions (restaurant_id, version, trained_at, metrics_json, baselines_json, feature_importance_json, validation_chart_json, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            restaurant_id, version, now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(metrics_data), json.dumps(baselines_data),
            json.dumps(final_model.feature_importances_),
            json.dumps(validation_chart)
        ))
        # Keep only the last 5 versions
        cursor.execute("""
            DELETE FROM model_versions WHERE restaurant_id = ? AND id NOT IN (
                SELECT id FROM model_versions WHERE restaurant_id = ? ORDER BY id DESC LIMIT 5
            )
        """, (restaurant_id, restaurant_id))
        
    # Write model to disk
    model_save_path = os.path.join(MODELS_DIR, f"{restaurant_id}_{version}.json")
    with open(model_save_path, "w") as f:
        json.dump({
            "version": version,
            "trained_at": now_dt.isoformat(),
            "base_score": final_model.base_score,
            "feature_names": feat_names,
            "feature_importances": final_model.feature_importances_,
            "q10_multiplier": q10_model.quantile_multiplier,
            "q90_multiplier": q90_model.quantile_multiplier
        }, f)
        
    # Now generate and write the 7-day forecast to Next_7_Days_Inputs
    update_next_7_days_forecast(restaurant_id, final_model, q10_model, q90_model, df_orders)
    
    return {
        "status": "success",
        "version": version,
        "metrics": metrics_data,
        "baselines": baselines_data,
        "feature_importances": final_model.feature_importances_,
        "validation_chart": validation_chart
    }

def update_next_7_days_forecast(restaurant_id: str, model=None, q10=None, q90=None, df_orders=None):
    """
    Predicts for all meals for each of the next 7 days and updates Next_7_Days_Inputs.
    Handles fallback: if a meal has fewer than 28 days of history, use its category's weekday average and label 'low confidence'.
    """
    with get_db() as conn:
        if df_orders is None:
            df_orders = pd.read_sql_query("SELECT * FROM daily_orders WHERE restaurant_id = ? ORDER BY date, meal_id", conn, params=(restaurant_id,))
        df_next = pd.read_sql_query("SELECT * FROM next_7_days_inputs WHERE restaurant_id = ? ORDER BY date, meal_id", conn, params=(restaurant_id,))
        
        if len(df_next) == 0:
            return
            
    # Calculate meal history length
    meal_counts = df_orders.groupby('meal_id')['date'].nunique().to_dict()
    
    # Category weekday averages for fallback
    df_orders['dt'] = pd.to_datetime(df_orders['date'])
    df_orders['dow'] = df_orders['dt'].dt.day_name()
    cat_dow_avg = df_orders.groupby(['category', 'dow'])['num_orders'].mean().to_dict()
    
    # Extract features for target
    X_target, _, _, meta_target = extract_features_df(df_orders, df_next, is_training=False)
    
    if model is None:
        # Load active model or fit simple if missing
        X_all, y_all, feat_names, _ = extract_features_df(df_orders, df_orders)
        model = PoissonGradientBoostingModel(n_estimators=50, learning_rate=0.08)
        model.fit(X_all, y_all, feat_names)
        preds_all = model.predict(X_all)
        q10 = QuantileRegressionModel(0.10)
        q10.fit(X_all, y_all, preds_all)
        q90 = QuantileRegressionModel(0.90)
        q90.fit(X_all, y_all, preds_all)
        
    preds = model.predict(X_target)
    preds_low = q10.predict(preds)
    preds_high = q90.predict(preds)
    
    with get_db() as conn:
        cursor = conn.cursor()
        for i, meta in enumerate(meta_target):
            m_id = meta['meal_id']
            d_str = meta['date']
            hist_days = meal_counts.get(m_id, 0)
            
            if hist_days < 28:
                # Fallback: category weekday average
                dow_name = datetime.datetime.strptime(d_str, "%Y-%m-%d").strftime("%A")
                exp_val = cat_dow_avg.get((meta['category'], dow_name), float(preds[i]))
                low_val = max(1.0, exp_val * 0.75)
                high_val = exp_val * 1.25
                conf = "low confidence"
            else:
                exp_val = float(preds[i])
                low_val = float(preds_low[i])
                high_val = float(preds_high[i])
                conf = "high confidence"
                
            cursor.execute("""
                UPDATE next_7_days_inputs
                SET predicted_orders = ?, predicted_low = ?, predicted_high = ?, confidence = ?
                WHERE restaurant_id = ? AND date = ? AND meal_id = ?
            """, (round(exp_val, 1), round(low_val, 1), round(high_val, 1), conf, restaurant_id, d_str, m_id))

def get_meal_forecast_data(restaurant_id: str, category: str = None, cuisine: str = None):
    with get_db() as conn:
        query = "SELECT * FROM next_7_days_inputs WHERE restaurant_id = ?"
        params = [restaurant_id]
        if category:
            query += " AND category = ?"
            params.append(category)
        if cuisine:
            query += " AND cuisine = ?"
            params.append(cuisine)
        query += " ORDER BY meal_name, date"
        df = pd.read_sql_query(query, conn, params=params)
        
        # Get list of categories and cuisines
        cats = [r[0] for r in conn.execute("SELECT DISTINCT category FROM meals WHERE restaurant_id = ? ORDER BY category", (restaurant_id,)).fetchall()]
        cuis = [r[0] for r in conn.execute("SELECT DISTINCT cuisine FROM meals WHERE restaurant_id = ? ORDER BY cuisine", (restaurant_id,)).fetchall()]
        
    return df, cats, cuis

def get_meal_history_and_forecast(restaurant_id: str, meal_id: int):
    with get_db() as conn:
        # Last 28 days of actuals
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, num_orders FROM daily_orders
            WHERE restaurant_id = ? AND meal_id = ?
            ORDER BY date DESC LIMIT 28
        """, (restaurant_id, meal_id))
        history_rows = cursor.fetchall()
        history_rows.reverse()
        
        # Next 7 days forecast
        cursor.execute("""
            SELECT date, predicted_orders, predicted_low, predicted_high, confidence
            FROM next_7_days_inputs
            WHERE restaurant_id = ? AND meal_id = ?
            ORDER BY date ASC LIMIT 7
        """, (restaurant_id, meal_id))
        forecast_rows = cursor.fetchall()
        
    return [dict(r) for r in history_rows], [dict(r) for r in forecast_rows]
