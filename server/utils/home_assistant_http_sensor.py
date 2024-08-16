"""A class to report the temperature to Home Assistant using HTTP sensor integration."""
import json
import logging
import time

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
SEND_INTERVAL_SECONDS = 60


class HomeAssistantHttpSensor:
    """A class to report the temperature to Home Assistant."""

    def __init__(self, entity_id: str, device_name: str, url: str, token: str):
        self.device_name = device_name
        self.entity_url = f"{url}/api/states/sensor.{entity_id}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.last_reported = 0.0

    def report_temperature(self, temperature: float):
        """Report the temperature to Home Assistant."""
        self._report_state("°C", f"{temperature:.2f}")

    def report_humidity(self, humidity: float):
        """Report the humidity to Home Assistant."""
        self._report_state("%", f"{humidity:.2f}")

    def _report_state(self, unit_of_measurement: str, state: str):
        """Report the temperature to Home Assistant."""

        if (time.time() - self.last_reported) < SEND_INTERVAL_SECONDS:
            return
        self.last_reported = time.time()

        body = {
            "state": str(state),
            "attributes": {
                "friendly_name": self.device_name,
                "unit_of_measurement": unit_of_measurement,
            },
        }
        try:
            response = requests.post(
                self.entity_url,
                headers=self.headers,
                json=body,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            curl_command = f"curl -X POST '{self.entity_url}'"
            for header, value in self.headers.items():
                curl_command += f" -H '{header}: {value}'"
            if body:
                curl_command += f" -d '{json.dumps(body)}'"

            error_message = (
                f"Request failed: {e}\nEquivalent cURL command: {curl_command}"
            )

            if e.response is not None:
                error_message += f"\nResponse content: {e.response.text}"

            logger.error(error_message)

    def __str__(self) -> str:
        return f"HomeAssistantHttpSensor({self.entity_url}): {self.device_name}"
