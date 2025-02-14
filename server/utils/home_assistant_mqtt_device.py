"""Home Assistant MQTT device for a thermometer"""

import logging
import time

from ha_mqtt_discoverable import DeviceInfo, Settings
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo

log = logging.getLogger(__name__)

DEFAULT_SEND_INTERVAL_SECONDS = 60


class ThermometerDevice:
    """Home Assistant MQTT device for a thermometer
    This is self-discoverable and doesn't require manual configuration in Home Assistant.
    """

    def __init__(
        self,
        mqtt_hostname: str,
        port: int,
        username: str,
        password: str,
        device_name: str,
        device_id: str,
        max_update_interval: int = DEFAULT_SEND_INTERVAL_SECONDS,
    ) -> None:
        self.max_update_interval = max_update_interval
        self.last_reported = 0.0

        # Configure the required parameters for the MQTT broker
        mqtt_settings = Settings.MQTT(
            host=mqtt_hostname, port=port, username=username, password=password
        )

        # Define the device. At least one of `identifiers` or `connections` must be supplied
        device_info = DeviceInfo(name=device_name, identifiers=device_id)

        # Sensor 1: air temperature
        # Associate the sensor with the device via the `device` parameter
        # `unique_id` must also be set, otherwise Home Assistant will not display
        # the device in the UI
        air_temperature_sensor_info = SensorInfo(
            name="Air temperature",
            device_class="temperature",
            unit_of_measurement="°C",
            state_class="measurement",
            unique_id="air_temperature_sensor",
            device=device_info,
        )
        air_temperature_settings = Settings(
            mqtt=mqtt_settings, entity=air_temperature_sensor_info
        )
        # Instantiate the sensor
        self.air_temperature_sensor = Sensor(air_temperature_settings)

        # Sensor 2: air humidity
        air_humidity_sensor_info = SensorInfo(
            name="Air humidity",
            device_class="humidity",
            unit_of_measurement="%",
            state_class="measurement",
            unique_id="air_humidity_sensor",
            device=device_info,
        )
        air_humidity_settings = Settings(
            mqtt=mqtt_settings, entity=air_humidity_sensor_info
        )
        # Instantiate the sensor
        self.air_humidity_sensor = Sensor(air_humidity_settings)

        # Sensor 3: water temperature
        water_temperature_sensor_info = SensorInfo(
            name="Water temperature",
            device_class="temperature",
            unit_of_measurement="°C",
            state_class="measurement",
            unique_id="water_temperature_sensor",
            device=device_info,
        )
        water_temperature_settings = Settings(
            mqtt=mqtt_settings, entity=water_temperature_sensor_info
        )
        # Instantiate the sensor
        self.water_temperature_sensor = Sensor(water_temperature_settings)

    def __str__(self) -> str:
        return "ThermometerDevice()"

    def report_measures(
        self, air_temperature: float, water_temperature: float, air_humidity: float
    ) -> None:
        """Report the sensor readings to Home Assistant."""
        current_time = time.time()
        if (current_time - self.last_reported) < self.max_update_interval:
            return
        self.last_reported = current_time

        try:
            self.air_temperature_sensor.set_state(round(air_temperature, 2))
            self.water_temperature_sensor.set_state(round(water_temperature, 2))
            self.air_humidity_sensor.set_state(round(air_humidity, 2))
        except Exception as e:
            log.error("Failed to report measures", exc_info=e)
            return
