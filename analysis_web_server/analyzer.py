import os
import json
import re
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect
from werkzeug.utils import secure_filename
import phonenumbers
from phonenumbers import PhoneNumberFormat

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads' # Folder to store uploaded CSV files
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) # Ensure the upload folder exists

# Global storage for the processed dataframe
df_analysis = None

def calculate_success_rate(call_result_str):
    '''Calculates the percentage of "OK" results in the call_result array of a modem survey'''
    try:
        # Handle cases where it might be a string representation of a list
        results = json.loads(call_result_str)
        if not results: return 0.0
        success_count = sum(
            1 for x in results
            if str(x).upper().startswith("OK")
        )
        return (success_count / len(results)) * 100
    except:
        return 0.0
    
def normalize_msisdn(number, region):
    """
    Normalize phone number to E.164 format without '+'.
    Returns None if invalid. Used in fuse endpoint to ensure consistent MSISDN comparison between SIMBOX events and phone call results.
    # Examples:
    # "IL" → Israel
    # "US" → United States
    # "CL" → Chile
    # "DE" → Germany
    # "FR" → France
    # "GB" → United Kingdom
    """

    if not number:
        return None

    try:
        parsed = phonenumbers.parse(str(number), region)

        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed,
                PhoneNumberFormat.E164
            ).replace("+", "")

    except:
        return None

    return None


@app.route('/')
def index():
    '''Renders the main analysis page where users can upload CSV files and visualize data'''
    return render_template('analysis.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    '''Endpoint to handle CSV file uploads and trigger analysis'''
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

    # Store original filename in dataframe attributes for reference
    df.attrs["source_file"] = filename 

    df_analysis = df
    return redirect('/')

@app.route('/get_data')
def get_data():
    '''Endpoint to provide processed data for frontend visualization'''
    global df_analysis
    if df_analysis is None: return jsonify({"error": "No data uploaded"})
    
    # Handle NaN and clean data
    df_clean = df_analysis.replace({float('nan'): None})
    df_clean['SUCCESS_RATE'] = df_clean['CALL_RESULT'].apply(calculate_success_rate)
    
    # Map Markers
    markers = df_clean.to_dict(orient='records')
    
    # Grid Logic - Group data into ~20m x 20m cells and calculate operator success rates and EARFCN/PCI distributions
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
    '''Endpoint to provide operator success rate data for a specific session (for chart visualization)'''
    global df_analysis
    filtered = df_analysis[df_analysis['SESSION_NAME'] == session]
    chart_data = filtered.groupby('OPERATOR')['SUCCESS_RATE'].mean().to_dict()
    return jsonify(chart_data)


############## ENDPOINTS FOR CHOOSING FILES FROM UPLOAD FOLDER ##############
@app.route('/list_uploads')
def list_uploads():
    '''Endpoint to list all uploaded CSV files for selection in the frontend'''
    files = [
        f for f in os.listdir(app.config['UPLOAD_FOLDER'])
        if f.lower().endswith('.csv')
    ]
    return jsonify(sorted(files))

@app.route('/load_file/<filename>')
def load_file(filename):
    '''Endpoint to load a selected CSV file from the uploads folder and re-process it for visualization'''
    global df_analysis

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"})

    df = pd.read_csv(filepath)
    df['SUCCESS_RATE'] = df['CALL_RESULT'].apply(calculate_success_rate)
    df.attrs["source_file"] = filename
    df_analysis = df

    return jsonify({"status": "loaded"})


######### ENDPOINT FOR FUSING PHONE CALL DATA INTO SIMBOX EVENTS ##############
@app.route('/fuse_results', methods=['POST'])
def fuse_results():
    '''Endpoint to fuse phone call results (from a JSON file) into the existing SIMBOX events dataframe based on MSISDN and timestamp proximity'''
    global df_analysis

    if df_analysis is None:
        return jsonify({"error": "No CSV loaded"})

    if 'file' not in request.files:
        return jsonify({"error": "No JSON file provided"})

    json_file = request.files['file']
    offset = int(request.form.get('offset', 0))
    region = request.form.get('region', 'IL')  # Default to 'IL' if not provided

    try:
        phone_results = json.load(json_file)
    except:
        return jsonify({"error": "Invalid JSON format"})

    df = df_analysis.copy()

    # Counters
    fused_count = 0
    no_match_count = 0
    already_ok_count = 0

    df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])

    # Normalize all MSISDNs in the dataframe once for comparison
    print("Using Region for normalization:", region)
    df['NORMALIZED_MSISDN'] = df['MODEM_MSISDN'].apply(
        lambda x: normalize_msisdn(x, region)
    )

    for row in phone_results:
        msisdn = re.sub(r'\D', '', str(row.get('msisdn')))

        event_time = pd.to_datetime(row.get('EVENT_TIME')) + pd.Timedelta(seconds=offset)

        df['MODEM_MSISDN'] = (
            df['MODEM_MSISDN']
            .astype(str)
            .str.replace(r'\D', '', regex=True)  # remove ALL non-digits
        )
        # Normalize the target MSISDN for comparison
        normalized_target = normalize_msisdn(row.get('msisdn'), region)

        # Find candidates with matching normalized MSISDN
        candidates = df[df['NORMALIZED_MSISDN'] == normalized_target]
        print(f"MSISDN COMPARE: {msisdn} = {df['MODEM_MSISDN'].unique()} | {len(candidates)} candidates found")

        matched = False

        for idx, sim_row in candidates.iterrows():
            time_diff = abs((sim_row['TIMESTAMP'] - event_time).total_seconds())
            if time_diff <= offset:
                try:
                    call_list = json.loads(sim_row['CALL_RESULT'])

                    # Find first non-OK
                    for i in range(len(call_list)):
                        if str(call_list[i]).upper() != "OK":
                            call_list[i] = "OK"
                            df.at[idx, 'CALL_RESULT'] = json.dumps(call_list)
                            fused_count += 1
                            matched = True
                            print(f"Fused MSISDN {msisdn} at index {idx} with time diff {time_diff:.1f}s. New call result array: {call_list}")
                            break
                    else:
                        already_ok_count += 1
                        matched = True

                    break

                except:
                    continue

        if not matched:
            no_match_count += 1

    # BACKUP ORIGINAL FILE
    original_filename = df_analysis.attrs.get("source_file")
    if not original_filename:
        return jsonify({"error": "Source filename not stored"})
    original_path = os.path.join(app.config['UPLOAD_FOLDER'], original_filename)

    if os.path.exists(original_path):
        backup_name = original_filename.replace(".csv", "_backup.csv")
        backup_path = os.path.join(app.config['UPLOAD_FOLDER'], backup_name)
        df_analysis.to_csv(backup_path, index=False)

    # Recalculate success rates after fusion
    df['SUCCESS_RATE'] = df['CALL_RESULT'].apply(calculate_success_rate)

    # OVERWRITE ORIGINAL
    df.to_csv(original_path, index=False)

    df.attrs["source_file"] = original_filename
    df_analysis = df

    return jsonify({
        "status": "done",
        "fused": fused_count,
        "no_match": no_match_count,
        "already_ok": already_ok_count
    })



# Start the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, debug=True)