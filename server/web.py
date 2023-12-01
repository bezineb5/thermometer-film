import argparse
import csv
import json
import logging
import threading
from datetime import datetime, timezone

import board
import busio

from flask import Flask, request, abort
from flask_socketio import SocketIO

from sensors import si7021, ds18b20
from process import development

log = logging.getLogger(__name__)
app = Flask(__name__)
socketio = SocketIO(app)

thread = None
thread_lock = threading.Lock()

air_sensor = None
water_sensor = None

dev_time_db = None
film_details = None

CONFIGURATION_FILE = "./config.json"
DX_NUMBER_KEY = "DX"
DEFAULT_DX_NUMBER = "017534"


@app.route("/")
def homepage():
    return app.send_static_file("index.html")


@app.route("/dx", methods=["GET", "POST"])
def dx_number():
    if request.method == "POST":
        content = request.json
        if content:
            dx_number = content.get("dx_number")
            if dx_number:
                new_film_details = dev_time_db.for_dx_number(dx_number)
                if new_film_details:
                    global film_details
                    film_details = new_film_details
                    _save_last_dx_number(film_details.dx_number)
                    return return_dx_number()
                abort(404)
        abort(403)
    else:  # GET
        return return_dx_number()


def return_dx_number():
    return {"dx_number": film_details.dx_number}


@socketio.on("connect", namespace="/temperature")
def temperature_connect():
    log.info("Client connected")
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(measure_thread)


@socketio.on("disconnect", namespace="/temperature")
def temperature_disconnect():
    log.info("Client disconnected")


def measure_thread():
    temperature_sensors = {
        "air": air_sensor,
        "water": water_sensor,
    }

    # Log file
    with open(
        f"temperature_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.csv",
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        fieldnames = ["time", "air", "water"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        while True:
            try:
                measurements = {
                    name: handler() for name, handler in temperature_sensors.items()
                }
                water_temp = measurements.get("water")
                air_temp = measurements.get("air")
                payload = {
                    "temperatures": [
                        {"id": "water", "temperature": water_temp},
                        {"id": "air", "temperature": air_temp},
                    ],
                }

                if water_temp is not None and film_details:
                    try:
                        duration_seconds = film_details.development_time(
                            water_temp
                        ).total_seconds()
                    except Exception as e:
                        log.error("Error calculating development time: %s", e)
                        duration_seconds = -1
                    payload["development"] = {
                        "duration": duration_seconds,
                        "film": {
                            "brand": film_details.brand,
                            "film_type": film_details.film_type,
                            "dx_number": film_details.dx_number,
                        },
                    }

                # Log to CSV
                csv_payload = {
                    "time": datetime.now(timezone.utc),
                    "air": air_temp,
                    "water": water_temp,
                }
                writer.writerow(csv_payload)
                f.flush()

                socketio.emit("measure", payload, namespace="/temperature")
            except:
                log.exception("Unable to read sensors")

            socketio.sleep(1.0)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Film development thermometer webapp")

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose mode")
    parser.add_argument(
        "--port", default="5000", type=int, help="Server port to listen to"
    )

    return parser.parse_args()


def _get_last_dx_number(default: str) -> str:
    value = default

    try:
        with open(CONFIGURATION_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            if config:
                value = config.get(DX_NUMBER_KEY, default)
    finally:
        return value


def _save_last_dx_number(last_dx_number: str):
    try:
        with open(CONFIGURATION_FILE, "w", encoding="utf-8") as f:
            data = {DX_NUMBER_KEY: last_dx_number}
            json.dump(data, f)
    finally:
        pass


def main():
    args = _parse_arguments()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)

    # Load film databases
    global dev_time_db, film_details
    dev_time_db = development.DevelopmentTime("./films.csv", "./chart_letters.csv")
    last_dx_number = _get_last_dx_number(DEFAULT_DX_NUMBER)
    log.info("Initial to DX number: %s", last_dx_number)
    film_details = dev_time_db.for_dx_number(last_dx_number)

    # Create the I2C bus
    i2c = busio.I2C(board.SCL, board.SDA)

    # Init the sensors
    global air_sensor, water_sensor
    air_sensor = si7021.init_si7021(i2c)
    water_sensor = ds18b20.init_ds18b20()

    # Web server
    socketio.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
