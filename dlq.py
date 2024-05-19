from prometheus_client import start_http_server, Gauge, CollectorRegistry
import paho.mqtt.client as mqtt
import tinytuya
import base64
import struct
import json
import time
import os

LISTEN_PORT = os.environ.get('LISTEN_PORT', 6666)
MQTT_PORT = os.environ.get('MQTT_PORT', 1883)
MQTT_BROKER = os.environ.get('MQTT_BROKER')
MQTT_USERNAME = os.environ.get('MQTT_USERNAME')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD')
tuya_api_key = os.environ.get('TUYA_API_KEY')
tuya_api_secret = os.environ.get('TUYA_API_SECRET')
tuya_device_id = os.environ.get('TUYA_DEVICE_ID')
update_interval = os.environ.get('UPDATE_INTERVAL', 30)

registry = CollectorRegistry()
dlq_voltage_gauge = Gauge('xiaobao_home_dlq_voltage', 'dlq voltage(V)', ['phase'])
dlq_current_gauge = Gauge('xiaobao_home_dlq_current', 'dlq current(A)', ['phase'])
dlq_power_gauge = Gauge('xiaobao_home_dlq_power', 'dlq power(kW)', ['phase'])
dlq_total_energy_gauge = Gauge('xiaobao_home_dlq_total_energy', 'dlq total energy(W)')

def mqtt_on_disconnect(client, userdata, rc):
    if rc != 0:
        while True:
            try:
                client.reconnect()
                break
            except:
                time.sleep(10)
                pass

def init_mqtt():
    try:
        client = mqtt.Client()
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.connect(MQTT_BROKER, int(MQTT_PORT), 2)
        client.on_disconnect = mqtt_on_disconnect
        client.loop_start()
        return client
    except Exception as e:
        print(e)

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
        print(e)
        return {}

def send_mqtt(topic, payload, client):
    print('state: ', client._state, 'loop: ', client._thread, end = ' ')
    try:
        topic = topic
        payload = payload
        qos = 0
        client.publish(topic, payload, qos)
        time.sleep(1)
    except Exception as e:
        print(e)
        print(topic)
        print(payload)

def build_discovery_payload(item):
    topic = "ecorehome/xiaobao/{item}/info".format(item=item)
    stype = 0
    unit = ""
    if "voltage" in item:
        stype = 20
        unit = "V"
    elif "current" in item:
        stype = 21
        unit = "A"
    elif "power" in item:
        stype = 22
        unit = "W"
    else:
        stype = 23
        unit = "kWh"

    payload = {
        "devid": "dlq_{item}".format(item=item),
        "model": 1,  
        "parentsid": "xiaobao_dlq", 
        "stype": stype,
        "unit": unit,
        "get_topic": "dlq/{item}/state".format(item=item),
        "dev": {
            "name": item,
            "vmodel": "xiaobao.dlq.tuya",
            "sw": "1.0.0",
            "manufacturer": "xiaobao"
        }
    }
    return topic, payload

def ecorehome_discovery(client):
    dlq_status = get_dlq_status()
    for phase in dlq_status["phase"]:
        for phase_item in dlq_status["phase"][phase].keys():
            discovery_payload = build_discovery_payload("{phase}_{phase_item}".format(phase=phase, phase_item=phase_item))
            print(discovery_payload)

            send_mqtt(discovery_payload[0], json.dumps(discovery_payload[1]), client)

    discovery_payload = build_discovery_payload("total_forward_energy")
    print(discovery_payload)

    send_mqtt(discovery_payload[0], json.dumps(discovery_payload[1]), client)

def metrics_update(client):
    while True:
        try:
            dlq_status = get_dlq_status()
            if dlq_status:
                for phase in dlq_status["phase"]:
                    state = dlq_status["phase"][phase]['voltage']
                    dlq_voltage_gauge.labels(phase).set(state)
                    send_mqtt("dlq/{item}_voltage/state".format(item=phase), json.dumps({"voltage": state}), client)

                    state = dlq_status["phase"][phase]['current']
                    dlq_current_gauge.labels(phase).set(dlq_status["phase"][phase]['current'])
                    send_mqtt("dlq/{item}_current/state".format(item=phase), json.dumps({"current": state}), client)

                    state = dlq_status["phase"][phase]['power']
                    dlq_power_gauge.labels(phase).set(dlq_status["phase"][phase]['power'])
                    send_mqtt("dlq/{item}_power/state".format(item=phase), json.dumps({"loadpower": float(state) * 1000}), client)

                state = dlq_status["total_forward_energy"] 
                dlq_total_energy_gauge.set(dlq_status["total_forward_energy"])
                send_mqtt("dlq/total_forward_energy/state".format(item=phase), json.dumps({"powerconsumed": float(state) / 100}), client)

        except Exception as e:
            print(e)

        time.sleep(int(update_interval))

if __name__ == '__main__':
    start_http_server(int(LISTEN_PORT))

    client = init_mqtt()
    if not client:
        while True:
            client = init_mqtt()
            time.sleep(10)

    ecorehome_discovery(client)
    metrics_update(client)
