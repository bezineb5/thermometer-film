import math

import busio
from adafruit_ads1x15 import ads1015, ads1115
from adafruit_ads1x15.analog_in import AnalogIn


def init_ads1015(i2c: busio.I2C):
    # Create the ADC object using the I2C bus
    ads = ads1015.ADS1015(i2c)
    return init_analog(ads, ads1015.P0)


def init_ads1115(i2c: busio.I2C):
    # Create the ADC object using the I2C bus
    ads = ads1115.ADS1115(i2c)
    return init_analog(ads, ads1115.P0)


def init_analog(ads, pin):
    rate = ads.rates[0]     # Slowest rate = highest precision
    ads.data_rate = rate
    ads.gain = 1    # +/- 4.096
    # Create single-ended input on channel 0
    chan = AnalogIn(ads, pin)

    def handler():
        return measure_analog(chan.voltage)

    return handler


# From https://stackoverflow.com/questions/44747996/arduino-temperature-sensor-counting-back
def measure_analog(voltage: float) -> float:
    raw_ADC = voltage / 3.3
    temp = math.log(10000.0/(1.0/raw_ADC-1.0))
    temp = 1.0 / (0.001129148 + (0.000234125 +
                                 (0.0000000876741 * temp * temp)) * temp)
    celsius = temp - 273.15  # Convert from Kelvin to Celsius
    return celsius
