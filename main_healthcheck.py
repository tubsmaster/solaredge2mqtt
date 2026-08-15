import logging
import queue
import sys

import paho.mqtt.client as mqtt

import yaml

yaml.SafeLoader.add_constructor('!secret', lambda loader, node: loader.construct_scalar(node))
# Open and parse the file
with open("config/configuration.yml", "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)
mqtt_config = config["mqtt"]

with open("config/secrets.yml", "r", encoding="utf-8") as file:
    config_secret = yaml.safe_load(file)


def healthcheck_mqtt():
    def get_single_mqtt_message():
        msg_queue = queue.Queue()
        topic = f"solaredge/modbus/#"
        timeout = 5

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                client.subscribe(topic)

        def on_message(client, userdata, msg):
            msg_queue.put(msg)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        client.on_connect = on_connect
        client.on_message = on_message

        try:
            client.username_pw_set(mqtt_config["username"], config_secret["mqtt_password"])
            client.connect(mqtt_config["broker"], mqtt_config["port"])
            client.loop_start()  # Runs the network loop in a background thread
            # Wait for a message up to `timeout` seconds
            msg = msg_queue.get(timeout=timeout)
            return msg.payload.decode("utf-8")
        except queue.Empty:
            print(f"Timeout: No message received on '{topic}' within {timeout}s.")
            return None
        except Exception as e:
            print(f"Connection error: {e}")
            return None
        finally:
            client.loop_stop()
            client.disconnect()

    payload = get_single_mqtt_message()
    mqtt_ok = bool(payload)
    return mqtt_ok


def main():
    mqtt_ok = healthcheck_mqtt()
    rc = 0 if mqtt_ok else 1
    if not mqtt_ok:
        logging.error(f"mqtt_ok = {mqtt_ok} - rc = {rc}")
    sys.exit(rc)


if __name__ == '__main__':
    main()
