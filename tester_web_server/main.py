from flask import Flask, render_template, request, jsonify, make_response
import mysql.connector
import json
from datetime import datetime
import logging
import csv
import io

app = Flask(__name__)

# --- Configuration ---
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 3306,
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
current_gps = {"lat": 0, "lng": 0, "alt": 0}
last_backend_activity = None # Tracks last time JSON was received
latest_modems = {}  # modem_number is latest modem status snapshot

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
                SESSION_NAME VARCHAR(255)
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

@app.route('/start_script', methods=['POST'])
def start_script():
    global system_mode, survey_running, modem_counter
    system_mode = 'start'
    survey_running = True
    modem_counter = 0
    return jsonify({"status": "start mode active"})

@app.route('/stop_script', methods=['POST'])
def stop_script():
    global system_mode, survey_running
    system_mode = 'stop'
    survey_running = False
    return jsonify({"status": "stop mode active"})

@app.route('/set_session', methods=['POST'])
def set_session():
    global session_name
    session_name = request.json.get('session_name', 'Default_Session')
    return jsonify({"status": "ok"})

@app.route('/update_gps', methods=['POST'])
def update_gps():
    global current_gps
    current_gps = request.json
    return jsonify({"status": "ok"})

@app.route('/get_status', methods=['GET'])
def get_status():
    return jsonify({
        "system_mode": system_mode,
        "survey_running": survey_running,
        "modem_counter": modem_counter,
        "session_name": session_name,
        "last_activity": last_backend_activity
    })

@app.route('/receive_json', methods=['POST'])
def receive_json():
    global modem_counter, last_backend_activity
    last_backend_activity = datetime.now().strftime("%H:%M:%S")
    
    data = request.json
    if not data: return jsonify({"error": "no data"}), 400


    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        senders = data.get('senders', {})
        
        for m_num, m_val in senders.items():
            modem_counter += 1
            survey = m_val.get('survey_results', {})

            # Keep latest live status per modem (for GUI)
            latest_modems[str(m_num)] = {
                "modem_number": int(m_num),
                "status": m_val.get("status"),
                "error": m_val.get("error"),
                "network": m_val.get("network"),
                "msisdn": m_val.get("msisdn"),
                "operator": survey.get("operator"),
                "rat": survey.get("rat"),
                "rssi": survey.get("rssi"),
                "snr": survey.get("snr"),
                "registration_status": survey.get("registration_status"),
                "last_seen": datetime.now().strftime("%H:%M:%S")
            }
            
            # Use data from payload, but use browser coordinates for DB
            cursor.execute('''
                INSERT INTO TBL_ST_SIMBOX_EVENTS (
                    MODEM_NUMBER, STATUS, ERROR, ERROR_CODE, MSISDN, SENT, MODEM_INDEX_I2C,
                    TIMESTAMP, NETWORK, USE_CALL, USE_SMS, IS_LOOPBACK_MSISDN, MODEM_MSISDN, MODEL, IMEI,
                    IMSI, REGISTRATION_STATUS, OPERATOR, RAT, ARFCN, BSIC, PSC, PCI, MCC,
                    MNC, LAC, CELL_ID, RSSI, SNR, CALL_RESULT, SMS_RESULT, LATITUDE, LONGITUDE, ALTITUDE, SESSION_NAME
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                int(m_num), m_val.get('status'), m_val.get('error'), m_val.get('error_code'),
                m_val.get('msisdn'), m_val.get('sent'), m_val.get('modem_index_i2c'),
                datetime.fromtimestamp(m_val.get('ts', datetime.now().timestamp())),
                m_val.get('network'), m_val.get('use_call'), m_val.get('use_sms'),
                m_val.get('is_loopback_msisdn'), m_val.get('modem_msisdn'),
                survey.get('model'), survey.get('imei'), survey.get('imsi'),
                survey.get('registration_status'), survey.get('operator'), survey.get('rat'),
                survey.get('arfcn'), survey.get('bsic'), survey.get('psc'), survey.get('pci'),
                survey.get('mcc'), survey.get('mnc'), survey.get('lac'), survey.get('cell_id'),
                survey.get('rssi'), survey.get('snr'),
                json.dumps(survey.get('call_result')), survey.get('sms_result'),
                current_gps['lat'], current_gps['lng'], current_gps.get('alt', 0),
                session_name
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"RECEIVE_JSON ERROR: {e}")
    
    # --- 2. Communication Logic (Command to Backend) ---
    if system_mode == 'stop':
        return jsonify({"status": "stop"}), 200
    
    return jsonify({"status": "start"}), 200
    

    
@app.route('/export_csv', methods=['GET'])
def export_csv():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        
        # Fetch all events
        cursor.execute("SELECT * FROM TBL_ST_SIMBOX_EVENTS ORDER BY TIMESTAMP DESC")
        rows = cursor.fetchall()
        
        # Get column names from cursor description
        column_names = [i[0] for i in cursor.description]
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(column_names) # Header
        writer.writerows(rows)        # Data
        
        # Create the response
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=simbox_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        response.headers["Content-type"] = "text/csv"
        
        cursor.close()
        conn.close()
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# Cleanup DB
@app.route('/cleanup_db', methods=['POST'])
def cleanup_db():
    try:
        data = request.json
        date = data.get("date")

        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        query = """
        DELETE FROM TBL_ST_SIMBOX_EVENTS
        WHERE TIMESTAMP < %s
        """

        cursor.execute(query, (date,))
        deleted = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": f"{deleted} records deleted before {date}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route('/get_modems', methods=['GET'])
def get_modems():
    ''' Modem data for gui modems tab'''
    modems = sorted(latest_modems.values(), key=lambda x: x["modem_number"])
    return jsonify({
        "count": len(modems),
        "modems": modems
    })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8990) # Internal port for Nginx
