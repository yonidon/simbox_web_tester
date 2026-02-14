import os
import json
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global storage for the processed dataframe
df_analysis = None

def calculate_success_rate(call_result_str):
    try:
        # Handle cases where it might be a string representation of a list
        results = json.loads(call_result_str)
        if not results: return 0.0
        success_count = sum(1 for x in results if str(x).upper() == "OK")
        return (success_count / len(results)) * 100
    except:
        return 0.0

@app.route('/')
def index():
    return render_template('analysis.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global df_analysis
    if 'file' not in request.files: return redirect('/')
    file = request.files['file']
    if file.filename == '': return redirect('/')
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Load and Process Data
    df = pd.read_csv(filepath)
    # Parse the call success rate
    df['SUCCESS_RATE'] = df['CALL_RESULT'].apply(calculate_success_rate)
    df_analysis = df
    return redirect('/')

@app.route('/get_data')
def get_data():
    global df_analysis
    if df_analysis is None: return jsonify({"error": "No data uploaded"})
    
    # Handle NaN and clean data
    df_clean = df_analysis.replace({float('nan'): None})
    df_clean['SUCCESS_RATE'] = df_clean['CALL_RESULT'].apply(calculate_success_rate)
    
    # Map Markers
    markers = df_clean.to_dict(orient='records')
    
    # Grid Logic (0.002 degree blocks)
    grid_size = 0.0002
    df_clean['grid_lat'] = (df_clean['LATITUDE'] / grid_size).apply(lambda x: round(x) * grid_size)
    df_clean['grid_lng'] = (df_clean['LONGITUDE'] / grid_size).apply(lambda x: round(x) * grid_size)
    
    grid_groups = df_clean.groupby(['grid_lat', 'grid_lng'])
    grid_data = []
    
    for (glat, glng), group in grid_groups:
        # 1. Success rate per operator in THIS cell
        op_stats = group.groupby('OPERATOR')['SUCCESS_RATE'].mean().round(1).to_dict()
        
        # 2. Local EARFCN + PCI Pair Distribution
        pair_dist = (
            group
            .groupby(['ARFCN', 'PCI'])
            .size()
            .div(len(group))
            .mul(100)
            .round(1)
        )

        # Convert multi-index to readable dictionary
        pair_dist_dict = {
            f"EARFCN {int(arfcn)} / PCI {int(pci)}": perc
            for (arfcn, pci), perc in pair_dist.items()
            if pd.notna(arfcn) and pd.notna(pci)
        }
        
        grid_data.append({
            "lat": glat,
            "lng": glng,
            "operators": op_stats,
            "pair_dist": pair_dist_dict,
            "total_samples": len(group)
        })

    return jsonify({
        "markers": markers,
        "grid": grid_data,
        "sessions": df_clean['SESSION_NAME'].unique().tolist()
    })

@app.route('/get_chart_data/<session>')
def get_chart_data(session):
    global df_analysis
    filtered = df_analysis[df_analysis['SESSION_NAME'] == session]
    chart_data = filtered.groupby('OPERATOR')['SUCCESS_RATE'].mean().to_dict()
    return jsonify(chart_data)


############## ENDPOINTS FOR CHOOSING FILES FROM UPLOAD FOLDER ##############
@app.route('/list_uploads')
def list_uploads():
    files = [
        f for f in os.listdir(app.config['UPLOAD_FOLDER'])
        if f.lower().endswith('.csv')
    ]
    return jsonify(sorted(files))

@app.route('/load_file/<filename>')
def load_file(filename):
    global df_analysis

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"})

    df = pd.read_csv(filepath)
    df['SUCCESS_RATE'] = df['CALL_RESULT'].apply(calculate_success_rate)
    df_analysis = df

    return jsonify({"status": "loaded"})



if __name__ == '__main__':
    app.run(port=9000, debug=True)