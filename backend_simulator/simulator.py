import requests
import random
import time
import json

# --- Configuration ---
# Match this to the port your Flask app is running on
SERVER_URL = "http://localhost:8990" 
POLL_INTERVAL = 3  # Seconds between each send

def generate_modem_payload(modem_number):
    """Generates random data for a single modem (logic from generate_test_payload.py)"""
    lat = round(random.uniform(32.085, 32.100), 6)
    lon = round(random.uniform(34.840, 34.860), 6)
    alt = round(random.uniform(40.0, 50.0), 1)
    
    call_result = random.choice([
        ["failed_timeout", "failed_timeout"],
        ["OK", "failed_timeout"],
        ["OK", "OK"],
        ["OK", "failed_timeout", "failed_timeout"]
    ])

    return {
        "status": "IDLE",
        "error": "",
        "error_code": 0,
        "msisdn": "+56962515275",
        "sent": 0,
        "modem_index_i2c": modem_number,
        "ts": time.time(),
        "network": "auto",
        "use_call": 1,
        "use_sms": 0,
        "is_loopback_msisdn": 0,
        "modem_msisdn": f"+569123456{modem_number:02}",
        "survey_results": {
            "model": "Quectel EG25",
            "imei": f"8679290685{random.randint(10000, 99999)}",
            "imsi": f"73001145584{random.randint(1000, 9999)}",
            "registration_status": str(random.choice(["1", "3", "5"])),
            "operator": "Operator X",
            "rat": "LTE",
            "arfcn": str(random.randint(9000, 10000)),
            "bsic": "", "psc": "", "pci": str(random.randint(1, 100)),
            "mcc": "730", "mnc": "02",
            "lac": str(random.randint(1000, 9999)),
            "cell_id": str(random.randint(10000, 999999)),
            "rssi": str(random.randint(-120, -50)),
            "snr": str(random.randint(-20, 0)),
            "call_result": call_result,
            "sms_result": "",
            "gps_location": f"{lat},{lon},{alt}"
        }
    }

def get_system_status():
    """Polls the webserver to see if we should be in 'start' or 'stop' mode"""
    try:
        response = requests.get(f"{SERVER_URL}/get_status", timeout=2)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Waiting for server... ({e})")
    return None

def run_simulator():
    print(f"Starting SIMBOX Simulator targeting {SERVER_URL}...")
    
    while True:
        status_data = get_system_status()
        
        if status_data:
            mode = status_data.get("system_mode", "stop")
            
            if mode == "start":
                # GENERATE FULL PAYLOAD
                num_modems = random.randint(1, 16) # Simulate varying modem counts
                payload = {
                    "simbox_name": "PC",
                    "psms_name": "PSMS",
                    "status": "RUNNING",
                    "gps_location": "0,0,0", # Server will override this anyway
                    "survey_running": True,
                    "senders": {str(i): generate_modem_payload(i) for i in range(1, num_modems + 1)}
                }
                print(f"[{time.strftime('%H:%M:%S')}] Sending ACTIVE payload ({num_modems} modems)")
            else:
                # GENERATE IDLE PAYLOAD
                payload = {
                    "simbox_name": "PC", 
                    "psms_name": "PSMS", 
                    "status": "IDLE", 
                    "senders": {}, 
                    "gps_location": "", 
                    "survey_running": False, 
                    "battery_voltage": 8.314, 
                    "battery_status": "Discharging"
                }
                print(f"[{time.strftime('%H:%M:%S')}] Sending IDLE heartbeat")

            # Send to server
            try:
                requests.post(f"{SERVER_URL}/receive_json", json=payload, timeout=2)
            except Exception as e:
                print(f"Error sending data: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_simulator()
