"""SI7021 temperature and humidity sensor module."""

import adafruit_si7021


def init_si7021(i2c):
    """Initialize the SI7021 temperature sensor."""
    sensor = adafruit_si7021.SI7021(i2c)

    def handler():
        return sensor.temperature

    return handler


def init_si7021_humidity(i2c):
    """Initialize the SI7021 humidity sensor."""
    sensor = adafruit_si7021.SI7021(i2c)

    def handler():
        return sensor.relative_humidity

    return handler
