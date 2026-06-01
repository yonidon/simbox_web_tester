import json
import pandas as pd
from flask import Blueprint, jsonify, request

analysis_bp = Blueprint('analysis', __name__)


def _get_df():
    import sys
    return getattr(sys.modules.get('__main__'), 'df_analysis', None)


def _clean_category(series):
    def format_value(value):
        text = str(value).strip()
        try:
            numeric = float(text)
            if numeric.is_integer():
                return str(int(numeric))
        except ValueError:
            pass
        return text

    cleaned = series.dropna().apply(format_value)
    return cleaned[(cleaned != '') & (cleaned != '-1') & (cleaned.str.lower() != 'nan')]


def _success_rate_series(df):
    if 'SUCCESS_RATE' in df.columns:
        return pd.to_numeric(df['SUCCESS_RATE'], errors='coerce').fillna(0)

    def calculate(call_result):
        try:
            results = json.loads(call_result)
            if not results:
                return 0.0
            success_count = sum(1 for item in results if str(item).upper().startswith('OK'))
            return (success_count / len(results)) * 100
        except Exception:
            return 0.0

    return df['CALL_RESULT'].apply(calculate)


# ── Column list (used by the custom-query modal dropdown) ──────────────────

@analysis_bp.route('/analysis/columns')
def get_columns():
    df = _get_df()
    if df is None:
        return jsonify([])
    return jsonify(df.columns.tolist())


# ── Built-in query 1: ARFCN distribution (pie) ────────────────────────────

@analysis_bp.route('/analysis/arfcn_distribution')
def arfcn_distribution():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})

    counts = (
        df['ARFCN']
        .dropna()
        .astype(int).astype(str)
        .pipe(lambda s: s[s != '-1'])
        .value_counts()
    )

    top = counts.head(15)
    other = int(counts.iloc[15:].sum()) if len(counts) > 15 else 0

    labels = top.index.tolist()
    values = [int(v) for v in top.values]

    if other > 0:
        labels.append('Other')
        values.append(other)

    return jsonify({"labels": labels, "values": values})


# ── Built-in query 2: Successful calls by ARFCN (bar) ─────────────────────
# Mirrors: SELECT ARFCN, COUNT(*) FROM ... WHERE CALL_RESULT='OK' AND ARFCN<>'-1' GROUP BY ARFCN

@analysis_bp.route('/analysis/calls_by_arfcn')
def calls_by_arfcn():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})

    tmp = df[df['SUCCESS_RATE'] > 0].copy()
    tmp = tmp[tmp['ARFCN'].notna()]
    tmp['_arfcn'] = tmp['ARFCN'].astype(int).astype(str)
    filtered = tmp[tmp['_arfcn'] != '-1']
    grouped = (
        filtered.groupby('_arfcn')
        .size()
        .sort_values(ascending=False)
        .head(20)
    )

    return jsonify({
        "labels": grouped.index.tolist(),
        "values": [int(v) for v in grouped.values]
    })


# ── Built-in query 3: Successful calls by Operator (bar) ──────────────────
# Mirrors: SELECT OPERATOR, COUNT(*) FROM ... WHERE CALL_RESULT='OK' AND OPERATOR IS NOT NULL GROUP BY OPERATOR

@analysis_bp.route('/analysis/calls_by_operator')
def calls_by_operator():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})

    filtered = df[
        (df['SUCCESS_RATE'] > 0) &
        (df['OPERATOR'].notna()) &
        (df['OPERATOR'].astype(str).str.strip() != '')
    ]
    grouped = (
        filtered.groupby('OPERATOR')
        .size()
        .sort_values(ascending=False)
    )

    return jsonify({
        "labels": grouped.index.tolist(),
        "values": [int(v) for v in grouped.values]
    })


# ── Built-in query 4: Cell ID distribution (pie) ──────────────────────────

@analysis_bp.route('/analysis/cell_id_distribution')
def cell_id_distribution():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})
    if 'CELL_ID' not in df.columns:
        return jsonify({"error": "Column 'CELL_ID' not found"})

    counts = _clean_category(df['CELL_ID']).value_counts()

    top = counts.head(15)
    other = int(counts.iloc[15:].sum()) if len(counts) > 15 else 0

    labels = top.index.tolist()
    values = [int(v) for v in top.values]

    if other > 0:
        labels.append('Other')
        values.append(other)

    return jsonify({"labels": labels, "values": values, "label": "Samples"})


# ── Built-in query 5: Average RSSI level per Cell ID (bar) ────────────────

@analysis_bp.route('/analysis/avg_rssi_by_cell_id')
def avg_rssi_by_cell_id():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})
    if 'CELL_ID' not in df.columns or 'RSSI' not in df.columns:
        return jsonify({"error": "Columns 'CELL_ID' and 'RSSI' are required"})

    tmp = pd.DataFrame({
        'cell_id': _clean_category(df['CELL_ID']),
        'rssi': pd.to_numeric(df['RSSI'], errors='coerce')
    }).dropna()

    grouped = (
        tmp.groupby('cell_id')['rssi']
        .mean()
        .sort_values(ascending=True)
        .head(25)
        .round(1)
    )

    return jsonify({
        "labels": grouped.index.tolist(),
        "values": [float(v) for v in grouped.values],
        "label": "Average RSSI"
    })


# ── Built-in query 6: Call success rate by Cell ID (bar) ──────────────────

@analysis_bp.route('/analysis/call_success_by_cell_id')
def call_success_by_cell_id():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})
    if 'CELL_ID' not in df.columns:
        return jsonify({"error": "Column 'CELL_ID' not found"})

    tmp = pd.DataFrame({
        'cell_id': _clean_category(df['CELL_ID']),
        'success_rate': _success_rate_series(df)
    }).dropna()

    grouped = (
        tmp.groupby('cell_id')['success_rate']
        .mean()
        .sort_values(ascending=False)
        .head(25)
        .round(1)
    )

    return jsonify({
        "labels": grouped.index.tolist(),
        "values": [float(v) for v in grouped.values],
        "label": "Call Success Rate (%)"
    })


# ── Built-in query 7: Call success rates by hour of day (line) ────────────

@analysis_bp.route('/analysis/call_success_by_hour')
def call_success_by_hour():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})
    if 'TIMESTAMP' not in df.columns:
        return jsonify({"error": "Column 'TIMESTAMP' not found"})

    tmp = pd.DataFrame({
        'timestamp': pd.to_datetime(df['TIMESTAMP'], errors='coerce'),
        'success_rate': _success_rate_series(df)
    }).dropna()
    tmp['hour'] = tmp['timestamp'].dt.hour

    grouped = tmp.groupby('hour')['success_rate'].mean().reindex(range(24), fill_value=0).round(1)

    return jsonify({
        "labels": [f"{hour:02d}:00" for hour in grouped.index],
        "values": [float(v) for v in grouped.values],
        "label": "Call Success Rate (%)"
    })


# ── Custom query endpoint ──────────────────────────────────────────────────
# Body: { "title": "...", "group_by": "COLUMN", "filter": "pandas query expr", "chart_type": "bar|pie|line" }

@analysis_bp.route('/analysis/custom_query', methods=['POST'])
def custom_query():
    df = _get_df()
    if df is None:
        return jsonify({"error": "No data loaded"})

    body = request.get_json()
    group_by   = body.get('group_by', '')
    filter_expr = body.get('filter', '').strip()
    chart_type  = body.get('chart_type', 'bar')
    title       = body.get('title') or group_by

    if group_by not in df.columns:
        return jsonify({"error": f"Column '{group_by}' not found"})

    try:
        working = df.query(filter_expr) if filter_expr else df
    except Exception as e:
        return jsonify({"error": f"Invalid filter expression: {e}"})

    grouped = (
        working.groupby(working[group_by].astype(str))
        .size()
        .sort_values(ascending=False)
        .head(25)
    )

    return jsonify({
        "labels": grouped.index.tolist(),
        "values": [int(v) for v in grouped.values],
        "title": title,
        "chart_type": chart_type
    })
