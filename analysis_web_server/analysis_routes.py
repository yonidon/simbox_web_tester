import pandas as pd
from flask import Blueprint, jsonify, request

analysis_bp = Blueprint('analysis', __name__)


def _get_df():
    import sys
    return getattr(sys.modules.get('__main__'), 'df_analysis', None)


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