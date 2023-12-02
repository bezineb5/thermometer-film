import argparse
import csv
import json
import logging
import queue
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

import board
import busio

from flask import Flask, request, abort, Response

# from flask_socketio import SocketIO

from sensors import si7021, ds18b20
from process import development

log = logging.getLogger(__name__)
app = Flask(__name__)
# socketio = SocketIO(app)

# thread = None
# thread_lock = threading.Lock()

# air_sensor = None
# water_sensor = None


class AtomicThreadLocalQueuesList:
    """A thread-safe list of thread-local queues."""

    def __init__(self):
        self._list = []
        self._thread_local_queue = threading.local()
        self._lock = threading.Lock()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def acquire(self) -> queue.SimpleQueue:
        new_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._thread_local_queue.queue = new_queue
        with self._lock:
            self._list.append(new_queue)
        return new_queue

    def release(self):
        with self._lock:
            self._list.remove(self._thread_local_queue.queue)
        del self._thread_local_queue.queue

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._list) == 0

    def broadcast(self, payload):
        with self._lock:
            for q in self._list:
                q.put(payload)


class AtomicRef:
    def __init__(self, value=None):
        self._value = value
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            return self._value

    def set(self, value):
        with self._lock:
            self._value = value


subscribers = AtomicThreadLocalQueuesList()
is_stopping = threading.Event()

dev_time_db: Optional[development.DevelopmentTime] = None
film_details = AtomicRef()

CONFIGURATION_FILE = "./config.json"
DX_NUMBER_KEY = "DX"
DEFAULT_DX_NUMBER = "017534"
INTERVAL_BETWEEN_MEASUREMENTS_SECONDS = 1.0


@app.route("/")
def homepage():
    """Serve the homepage."""
    return app.send_static_file("index.html")


@app.route("/dx", methods=["GET", "POST"])
def dx_number_method():
    """Get or set the DX number for the film."""
    if request.method == "POST":
        content = request.json
        if content:
            dx_number = content.get("dx_number")
            if dx_number:
                new_film_details = dev_time_db.for_dx_number(dx_number)
                if new_film_details:
                    film_details.set(new_film_details)
                    _save_last_dx_number(new_film_details.dx_number)
                    return _return_dx_number()
                abort(404)
        abort(403)
    else:  # GET
        return _return_dx_number()


def _return_dx_number() -> Dict[str, Optional[str]]:
    details = film_details.get()
    if not details:
        dx_number = None
    else:
        dx_number = details.dx_number
    return {"dx_number": dx_number}


def event_stream():
    """Serve the sensors event stream."""
    log.info("Client connected")

    with subscribers as q:
        try:
            while not is_stopping.is_set():
                # No newline in the json payload, otherwise the client will not receive it
                json_payload = json.dumps(q.get())
                yield f"data: {json_payload}\n\n"  # send data to client
        except GeneratorExit:  # client disconnected
            log.info("Client disconnected")


@app.route("/stream")
def stream():
    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def _measure_thread(air_sensor, water_sensor):
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
        fieldnames = [
            "time",
        ] + sorted(list(temperature_sensors.keys()))
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        while not is_stopping.is_set():
            try:
                measurement_time = datetime.now(timezone.utc)
                measurements = {
                    name: handler() for name, handler in temperature_sensors.items()
                }
                payload = {
                    "temperatures": [
                        {"id": name, "temperature": value}
                        for name, value in measurements.items()
                    ],
                }

                water_temp = measurements.get("water")
                details = film_details.get()
                if water_temp is not None and details:
                    try:
                        duration_seconds = details.development_time(
                            water_temp
                        ).total_seconds()
                    except Exception as e:
                        log.error("Error calculating development time: %s", e)
                        duration_seconds = -1
                    payload["development"] = {
                        "duration": duration_seconds,
                        "film": {
                            "brand": details.brand,
                            "film_type": details.film_type,
                            "dx_number": details.dx_number,
                        },
                    }

                # Show in the UI
                subscribers.broadcast(payload)

                # Log to CSV
                csv_payload = {
                    "time": measurement_time,
                    **measurements,
                }
                writer.writerow(csv_payload)
                f.flush()
            except:
                log.exception("Unable to read sensors")

            time.sleep(INTERVAL_BETWEEN_MEASUREMENTS_SECONDS)


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
    except FileNotFoundError:
        log.info(
            "Configuration file '%s' not found, using default DX number",
            CONFIGURATION_FILE,
        )
    return value


def _save_last_dx_number(last_dx_number: str) -> None:
    try:
        with open(CONFIGURATION_FILE, "w", encoding="utf-8") as f:
            data = {DX_NUMBER_KEY: last_dx_number}
            json.dump(data, f)
    except:
        log.exception("Unable to save last DX number")


def _init_development_time_db():
    global dev_time_db
    dev_time_db = development.DevelopmentTime("./films.csv", "./chart_letters.csv")


def main():
    """Main entry point."""
    args = _parse_arguments()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)

    # Load film databases
    _init_development_time_db()
    last_dx_number = _get_last_dx_number(DEFAULT_DX_NUMBER)
    log.info("Initial to DX number: %s", last_dx_number)
    film_details.set(dev_time_db.for_dx_number(last_dx_number))

    # Create the I2C bus
    i2c = busio.I2C(board.SCL, board.SDA)

    # Init the sensors
    air_sensor = si7021.init_si7021(i2c)
    water_sensor = ds18b20.init_ds18b20()

    # Start measuring thread
    threading.Thread(
        target=_measure_thread, args=(air_sensor, water_sensor), daemon=False
    ).start()

    # Web server
    app.run(host="0.0.0.0", port=args.port, threaded=True)
    # socketio.run(app, host="0.0.0.0", port=args.port)

    is_stopping.set()


if __name__ == "__main__":
    main()
