from prometheus_client import start_http_server, Gauge, CollectorRegistry
import tinytuya
import base64
import struct
import time
import os

PORT = os.environ.get('LISTEN_PORT', 6666)
tuya_api_key = os.environ.get('TUYA_API_KEY')
tuya_api_secret = os.environ.get('TUYA_API_SECRET')
tuya_device_id = os.environ.get('TUYA_DEVICE_ID')
update_interval = os.environ.get('UPDATE_INTERVAL', 60)

registry = CollectorRegistry()
dlq_voltage_gauge = Gauge('xiaobao_home_dlq_voltage', 'dlq voltage(V)', ['phase'])
dlq_current_gauge = Gauge('xiaobao_home_dlq_current', 'dlq current(A)', ['phase'])
dlq_power_gauge = Gauge('xiaobao_home_dlq_power', 'dlq power(kW)', ['phase'])
dlq_total_energy_gauge = Gauge('xiaobao_home_dlq_total_energy', 'dlq total energy(W)')

def get_dlq_status():
    c = tinytuya.Cloud(
        apiRegion="cn",
        apiKey=tuya_api_key,
        apiSecret=tuya_api_secret)

    device_id=tuya_device_id
    
    try:
        status=c.getstatus(device_id)
        if status.get("success", False):
            _status = {"phase": {}, "total_forward_energy": 0}
            for i in status.get("result",[]):
                if "phase_" in i.get("code"):
                    __raw = base64.b64decode(i.get("value"))
                    voltage = struct.unpack('>H', __raw[0:2])[0] / 10.0
                    current = struct.unpack('>L', b'\x00' + __raw[2:5])[0] / 1000.0
                    power = struct.unpack('>L', b'\x00' + __raw[5:8])[0] / 1000.0
                    _status["phase"][i.get("code")] = {
                        "voltage": str(voltage),
                        "current": str(current),
                        "power": str(power)
                    }

                if "total_forward_energy" in i.get("code"):
                    _status[i.get("code")] = i.get("value")
            return _status
        return {}

    except Exception as e:
        print(str(e))
        return {}

def metrics_update():
    while True:
        dlq_status = get_dlq_status()
        if dlq_status:
            print(dlq_status)
            for phase in dlq_status["phase"]:
                dlq_voltage_gauge.labels(phase).set(dlq_status["phase"][phase]['voltage'])
                dlq_current_gauge.labels(phase).set(dlq_status["phase"][phase]['current'])
                dlq_power_gauge.labels(phase).set(dlq_status["phase"][phase]['power'])
            dlq_total_energy_gauge.set(dlq_status["total_forward_energy"])
        time.sleep(int(update_interval))

if __name__ == '__main__':
    start_http_server(int(PORT))
    metrics_update()
