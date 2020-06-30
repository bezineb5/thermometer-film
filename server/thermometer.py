import argparse
import time
from collections import OrderedDict
from datetime import timedelta
from functools import lru_cache
from typing import Dict, Tuple

from io import BytesIO
from picamera import PiCamera
from PIL import Image, ImageDraw, ImageFont
from pyzbar import pyzbar

import adafruit_ssd1306
import board
import busio
import digitalio

from sensors import analog, si7021, ds18b20
from process import development

WHITE = 255
BLACK = 0

DX_NUMBER = "017534"


def main():
    args = _parse_arguments()
    barcode = DX_NUMBER

    # Create the I2C bus
    i2c = busio.I2C(board.SCL, board.SDA)

    # Create the SPI bus
    spi = busio.SPI(board.SCK, MOSI=board.MOSI)

    # Initialize the screen
    screen = init_screen(spi)

    # Initialize the scanner
    if args.barcode:
        barcode_scanner = init_barcode_scanner()
    else:
        barcode_scanner = lambda: ""

    # Initialize the temperature sensors
    temperature_sensors = OrderedDict()
    if args.ads1015:
        temperature_sensors['ADS1015'] = analog.init_ads1015(i2c)
    if args.ads1115:
        temperature_sensors['ADS1115'] = analog.init_ads1115(i2c)
    if args.si7021:
        temperature_sensors['Si7021'] = si7021.init_si7021(i2c)
    if args.ds18b20:
        temperature_sensors['DS18B20'] = ds18b20.init_ds18b20()

    dev_time_db = development.DevelopmentTime("./films.csv", "./chart_letters.csv")
    film_details = dev_time_db.for_dx_number(DX_NUMBER)

    while True:
        new_barcode = barcode_scanner()
        if new_barcode:
            barcode = new_barcode

        measurements = OrderedDict()
        for name, handler in temperature_sensors.items():
            try:
                temp = handler()
                duration = film_details.development_time(temp)
                measurements[name] = (temp, duration)
                print("{}\t{:>5.3f}\t{}".format(name, temp, _timedelta_to_string(duration)))
            except:
                print("Unable to read sensor: {}".format(name))

        display_temperatures(screen, measurements, str(film_details))

        time.sleep(1.0)


def init_screen(spi: busio.SPI) -> adafruit_ssd1306.SSD1306_SPI:
    reset_pin = digitalio.DigitalInOut(board.D27)  # any pin!
    cs_pin = digitalio.DigitalInOut(board.D22)    # any pin!
    dc_pin = digitalio.DigitalInOut(board.D17)    # any pin!

    oled = adafruit_ssd1306.SSD1306_SPI(
        128, 64, spi, dc_pin, reset_pin, cs_pin)

    # Clear display.
    oled.fill(0)
    oled.show()

    return oled


@lru_cache(maxsize=1)
def get_font():
    # Load default font.
    return ImageFont.load_default()


def display_temperatures(oled: adafruit_ssd1306.SSD1306_SPI, temperatures: Dict[str, Tuple[float, timedelta]], film_type: str) -> None:
    # Prepare text
    text = '\n'.join(["{}:\t{:>5.3f}ºC > {}".format(name[:3], temp, _timedelta_to_string(duration)) for name, (temp, duration) in temperatures.items()])
    text = "Film type: " + film_type + "\n" + text

    # Create blank image for drawing.
    # Make sure to create image with mode '1' for 1-bit color.
    image = Image.new("1", (oled.width, oled.height))

    # Get drawing object to draw on image.
    draw = ImageDraw.Draw(image)

    # Draw a black background
    draw.rectangle((0, 0, oled.width, oled.height), outline=BLACK, fill=BLACK)

    # Draw Some Text
    font = get_font()
    draw.text(
        (0, 0),
        text,
        font=font,
        fill=WHITE,
    )

    # Display image
    oled.image(image)
    oled.show()

def init_barcode_scanner():
    camera = PiCamera()
    camera.resolution = (2592, 1944)
    # camera.start_preview()

    def scan():
        stream = BytesIO()
        camera.capture(stream, format='jpeg')
        # "Rewind" the stream to the beginning so we can read its content
        stream.seek(0)
        image = Image.open(stream)

        barcodes = pyzbar.decode(image)
        print(barcodes)
        if barcodes:
            return str(barcodes[0].data.decode('ascii'))
    
    return scan

def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Thermometer')

    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose mode')
    parser.add_argument('--ads1115', action='store_true', help='VMA320 on ADS1115')
    parser.add_argument('--ads1015', action='store_true', help='VMA320 on ADS1015')
    parser.add_argument('--si7021', action='store_true', help='Si7021')
    parser.add_argument('--ds18b20', action='store_true', help='DS18B20')
    parser.add_argument('--barcode', action='store_true', help='Enable barcode scanner')
    return parser.parse_args()


def _timedelta_to_string(td: timedelta) -> str:
    minutes, seconds = divmod(int(td.total_seconds()), 60)

    # Formatted only for hours and minutes as requested
    return f"{minutes:2}:{seconds:02}"

if __name__ == "__main__":
    main()
