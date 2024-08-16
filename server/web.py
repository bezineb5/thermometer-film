import argparse
import csv
import json
import logging
import time
import threading
import pathlib
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, Type

import board
import busio

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
    JsonConfigSettingsSource,
)
from flask import Flask, request, abort, Response

from sensors import si7021, ds18b20
from process import development
from utils.atomic import AtomicThreadLocalQueuesList, AtomicRef
from utils import home_assistant_http_sensor

CONFIGURATION_FILE = "./config.json"
MEASURE_LOG_DIR = "./measurements"
DEFAULT_DX_NUMBER = "017534"
INTERVAL_BETWEEN_MEASUREMENTS_SECONDS = 1.0

log = logging.getLogger(__name__)
app = Flask(__name__)

subscribers = AtomicThreadLocalQueuesList()
is_stopping = threading.Event()

dev_time_db: Optional[development.DevelopmentTime] = None
film_details = AtomicRef()
ha_temperature_service: Optional[
    home_assistant_http_sensor.HomeAssistantHttpSensor
] = None
ha_humidity_service: Optional[home_assistant_http_sensor.HomeAssistantHttpSensor] = None


class HomeAssistantService(BaseModel):
    entity_id: str = ""
    device_name: str = ""
    url: str = ""
    token: str = ""


class Settings(BaseSettings):
    dx_number: str = DEFAULT_DX_NUMBER
    home_assistant_temperature_service: HomeAssistantService = HomeAssistantService()
    home_assistant_humidity_service: HomeAssistantService = HomeAssistantService()

    model_config = SettingsConfigDict(
        json_file=CONFIGURATION_FILE,
        json_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (JsonConfigSettingsSource(settings_cls),)


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


def _event_stream():
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
    """Endpoint for the Server-Sent Events (SSE) stream of temperature measurements."""
    response = Response(_event_stream(), mimetype="text/event-stream")
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def _measure_thread(air_sensor, water_sensor, humidity_sensor=None):
    temperature_sensors = {
        "air": air_sensor,
        "water": water_sensor,
    }

    # Measurements log file
    log_dir = pathlib.Path(MEASURE_LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (
        log_dir
        / f"temperature_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.csv"
    )

    with open(
        log_file,
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
                humidity_measurement = humidity_sensor() if humidity_sensor else None
                payload = {
                    "temperatures": [
                        {"id": name, "temperature": value}
                        for name, value in measurements.items()
                    ],
                }
                if humidity_measurement is not None:
                    payload["humidity"] = {
                        "id": "air",
                        "humidity": humidity_measurement,
                    }

                water_temp = measurements.get("water")
                details = film_details.get()
                if water_temp is not None and details:
                    error = None
                    try:
                        duration_seconds = details.development_time(
                            water_temp
                        ).total_seconds()
                    except development.UserError as e:
                        log.info("Unable to calculate development time: %s", e)
                        duration_seconds = -1
                        error = str(e)
                    except Exception as e:
                        log.error("Error calculating development time: %s", e)
                        duration_seconds = -1
                        error = "Internal error"
                    payload["development"] = {
                        "duration": duration_seconds,
                        "film": {
                            "brand": details.brand,
                            "film_type": details.film_type,
                            "dx_number": details.dx_number,
                        },
                    }
                    if error:
                        payload["development"]["error"] = error

                # Show in the UI
                subscribers.broadcast(payload)

                # Log to CSV
                csv_payload = {
                    "time": measurement_time,
                    **measurements,
                }
                writer.writerow(csv_payload)
                f.flush()

                # Report to Home Assistant
                if ha_temperature_service:
                    ha_temperature_service.report_temperature(
                        temperature_sensors["air"]()
                    )
                if ha_humidity_service and humidity_measurement is not None:
                    ha_humidity_service.report_humidity(humidity_measurement)
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


def _read_configuration() -> Settings:
    return Settings()


def _get_last_dx_number(settings: Settings, default: str) -> str:
    if settings.dx_number:
        return settings.dx_number
    return default


def _save_last_dx_number(last_dx_number: str) -> None:
    settings = _read_configuration()
    settings.dx_number = last_dx_number
    try:
        with open(CONFIGURATION_FILE, "w", encoding="utf-8") as f:
            data = settings.model_dump()
            json.dump(data, f)
    except:
        log.exception("Unable to save last DX number")


def _is_ha_config_valid(ha_service: HomeAssistantService) -> bool:
    return (
        ha_service
        and ha_service.entity_id
        and ha_service.device_name
        and ha_service.url
        and ha_service.token
    )


def _configure_home_assistant(settings: Settings):
    ha_temperature_settings = settings.home_assistant_temperature_service
    if _is_ha_config_valid(ha_temperature_settings):
        global ha_temperature_service
        ha_temperature_service = home_assistant_http_sensor.HomeAssistantHttpSensor(
            entity_id=ha_temperature_settings.entity_id,
            device_name=ha_temperature_settings.device_name,
            url=ha_temperature_settings.url,
            token=ha_temperature_settings.token,
        )
        log.info(
            "Home Assistant configuration (temperature): %s", ha_temperature_service
        )
    ha_humidity_settings = settings.home_assistant_humidity_service
    if _is_ha_config_valid(ha_humidity_settings):
        global ha_humidity_service
        ha_humidity_service = home_assistant_http_sensor.HomeAssistantHttpSensor(
            entity_id=ha_humidity_settings.entity_id,
            device_name=ha_humidity_settings.device_name,
            url=ha_humidity_settings.url,
            token=ha_humidity_settings.token,
        )
        log.info("Home Assistant configuration (humidity): %s", ha_humidity_service)


def _init_development_time_db():
    global dev_time_db
    dev_time_db = development.DevelopmentTime("./films.csv", "./chart_letters.csv")


def main():
    """Main entry point."""
    args = _parse_arguments()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)

    # Configure Home Assistant
    settings = _read_configuration()
    _configure_home_assistant(settings)

    # Load film databases
    _init_development_time_db()
    last_dx_number = _get_last_dx_number(settings, DEFAULT_DX_NUMBER)
    log.info("Initial DX number: %s", last_dx_number)
    film_details.set(dev_time_db.for_dx_number(last_dx_number))

    # Create the I2C bus
    i2c = busio.I2C(board.SCL, board.SDA)

    # Init the sensors
    air_sensor = si7021.init_si7021(i2c)
    water_sensor = ds18b20.init_ds18b20()
    humidity_sensor = si7021.init_si7021_humidity(i2c)

    # Start measuring thread
    threading.Thread(
        target=_measure_thread,
        args=(air_sensor, water_sensor, humidity_sensor),
        daemon=False,
    ).start()

    # Web server
    app.run(host="0.0.0.0", port=args.port, threaded=True)

    is_stopping.set()


if __name__ == "__main__":
    main()
