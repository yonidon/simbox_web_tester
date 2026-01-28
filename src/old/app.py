from flask import Flask, render_template, request, jsonify
import mysql.connector
import json
from datetime import datetime

app = Flask(__name__)

# --- Configuration ---
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': '3306',
    'user': 'sgb',
    'password': 'sgb',
    'database': 'sgb',
    'auth_plugin': 'mysql_native_password'  # FIXES THE AUTH ERROR
}

# --- Global State ---
system_mode = 'stop'
survey_running = False
session_name = "Default_Session"
modem_counter = 0
current_gps = {"lat": 0, "lng": 0, "alt": 0, "status": "Waiting..."}

def init_db():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS TBL_ST_SIMBOX_EVENTS (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                MODEM_NUMBER INT,
                STATUS VARCHAR(255),
                ERROR VARCHAR(255),
                ERROR_CODE INT,
                MSISDN VARCHAR(255),
                SENT INT,
                MODEM_INDEX_I2C INT,
                TIMESTAMP DATETIME,
                NETWORK VARCHAR(255),
                USE_CALL INT,
                USE_SMS INT,
                IS_LOOPBACK_MSISDN INT,
                MODEM_MSISDN VARCHAR(255),
                MODEL VARCHAR(255),
                IMEI VARCHAR(255),
                IMSI VARCHAR(255),
                REGISTRATION_STATUS VARCHAR(255),
                OPERATOR VARCHAR(255),
                RAT VARCHAR(255),
                ARFCN VARCHAR(255),
                BSIC VARCHAR(255),
                PSC VARCHAR(255),
                PCI VARCHAR(255),
                MCC VARCHAR(255),
                MNC VARCHAR(255),
                LAC VARCHAR(255),
                CELL_ID VARCHAR(255),
                RSSI VARCHAR(255),
                SNR VARCHAR(255),
                CALL_RESULT VARCHAR(255),
                SMS_RESULT VARCHAR(255),
                LATITUDE DECIMAL(13,5),
                LONGITUDE DECIMAL(11,5),
                ALTITUDE  DECIMAL(6,1),
                SESSION_NAME VARCHAR(255),
                INDEX idx_timestamp (TIMESTAMP)
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database Init Error: {e}")

@app.route('/')
def index():
    return render_template('index.html')

# --- Control Endpoints ---

@app.route('/start_script', methods=['POST'])
def start_script():
    global system_mode, survey_running, modem_counter
    system_mode = 'start'
    survey_running = True
    modem_counter = 0  # Reset counter on start
    return jsonify({"status": "start mode active", "survey_running": True})

@app.route('/stop_script', methods=['POST'])
def stop_script():
    global system_mode, survey_running
    system_mode = 'stop'
    survey_running = False
    return jsonify({"status": "stop mode active", "survey_running": False})

@app.route('/set_session', methods=['POST'])
def set_session():
    global session_name
    data = request.json
    session_name = data.get('session_name', 'Default_Session')
    return jsonify({"status": "session updated", "name": session_name})

@app.route('/update_gps', methods=['POST'])
def update_gps():
    global current_gps
    current_gps = request.json
    return jsonify({"status": "gps updated"})

@app.route('/get_status', methods=['GET'])
def get_status():
    return jsonify({
        "system_mode": system_mode,
        "survey_running": survey_running,
        "modem_counter": modem_counter,
        "session_name": session_name
    })

# --- Data Receiver ---

@app.route('/receive_json', methods=['POST'])
def receive_json():
    global modem_counter
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    senders = data.get('senders', {})
    
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        
        for modem_number, modem_data in senders.items():
            modem_counter += 1
            readable_timestamp = datetime.fromtimestamp(modem_data.get('ts', datetime.now().timestamp()))
            survey = modem_data.get('survey_results', {})

            cursor.execute('''
                INSERT INTO TBL_ST_SIMBOX_EVENTS (
                    MODEM_NUMBER, STATUS, ERROR, ERROR_CODE, MSISDN, SENT, MODEM_INDEX_I2C,
                    TIMESTAMP, NETWORK, USE_CALL, USE_SMS, IS_LOOPBACK_MSISDN, MODEM_MSISDN, MODEL, IMEI,
                    IMSI, REGISTRATION_STATUS, OPERATOR, RAT, ARFCN, BSIC, PSC, PCI, MCC,
                    MNC, LAC, CELL_ID, RSSI, SNR, CALL_RESULT, SMS_RESULT, LATITUDE, LONGITUDE, ALTITUDE, SESSION_NAME 
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                modem_number, modem_data['status'], modem_data['error'], modem_data['error_code'],
                modem_data['msisdn'], modem_data['sent'], modem_data['modem_index_i2c'], readable_timestamp,
                modem_data['network'], modem_data['use_call'], modem_data['use_sms'], modem_data['is_loopback_msisdn'], modem_data['modem_msisdn'],
                survey.get('model'), survey.get('imei'),
                survey.get('imsi'), survey.get('registration_status'),
                survey.get('operator'), survey.get('rat'),
                survey.get('arfcn'), survey.get('bsic'),
                survey.get('psc'), survey.get('pci'),
                survey.get('mcc'), survey.get('mnc'),
                survey.get('lac'), survey.get('cell_id'),
                survey.get('rssi'), survey.get('snr'),
                json.dumps(survey.get('call_result', [])), survey.get('sms_result'),
                current_gps['lat'], current_gps['lng'], current_gps['alt'],
                session_name 
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "processed": len(senders)})
    
    except Exception as e:
        print(f"DB Insert Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8990, debug=True)
