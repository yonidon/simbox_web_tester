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

def run_simulator():
    print(f"Starting SIMBOX Simulator targeting {SERVER_URL}...")
    current_mode = "stop" # Default state

    while True:
        # 1. Prepare payload based on the current mode
        if current_mode == "start":
            num_modems = random.randint(1, 16)
            payload = {
                "simbox_name": "PC",
                "psms_name": "PSMS",
                "status": "RUNNING",
                "gps_location": "0,0,0",
                "survey_running": True,
                "senders": {str(i): generate_modem_payload(i) for i in range(1, num_modems + 1)}
            }
            print(f"[{time.strftime('%H:%M:%S')}] Mode: START | Sending Active Data ({num_modems} modems)")
        else:
            payload = {
                "simbox_name": "PC", 
                "psms_name": "PSMS", 
                "status": "IDLE", 
                "senders": {}, 
                "gps_location": "", 
                "survey_running": False
            }
            print(f"[{time.strftime('%H:%M:%S')}] Mode: STOP | Sending Heartbeat")

        # 2. Send payload and receive the command for the NEXT loop
        try:
            # We use POST for both sending data AND receiving the next instruction
            response = requests.post(f"{SERVER_URL}/receive_json", json=payload, timeout=5)
            
            if response.status_code == 200:
                # Capture the "start" or "stop" status from server response
                server_response = response.json()
                current_mode = server_response.get("status", "stop")
            else:
                print(f"Server error: {response.status_code}")
                
        except Exception as e:
            print(f"Connection error: {e}")

        # 3. Wait before checking in again
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_simulator()
