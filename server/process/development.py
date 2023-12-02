"""Development time calculator."""
import csv
import re
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)


class UserError(Exception):
    """An error that should be reported to the user."""

    pass


@dataclass(frozen=True)
class FilmDetails:
    """Details about a film, including the development time calculator."""

    brand: str
    film_type: str
    dx_number: str
    evaluator: Callable[[float], timedelta]

    def __str__(self) -> str:
        return f"{self.brand} {self.film_type}"

    def development_time(self, temp_celsius: float) -> timedelta:
        """Return the development time for the given temperature in celsius."""
        return self.evaluator(temp_celsius)


def _read_films(
    csv_filename: str, durations_map: Dict[str, Callable[[float], timedelta]]
):
    with open(csv_filename, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            brand = row["Brand"]
            film_type = row["Film Type"]
            dx_number = row["DX Number"]
            chart_letter = row["Chart Letter"]
            evaluator = durations_map[chart_letter]

            yield FilmDetails(
                brand=brand,
                film_type=film_type,
                dx_number=dx_number,
                evaluator=evaluator,
            )


def _parse_temperatures_header(header_row) -> List[float]:
    if header_row[0] != "Chart Letter":
        raise ValueError("Expected: Chart Letter")

    temp_re = re.compile("^([+-]?\\d*[.,]?\\d*)°C$")

    def parse_temp(temp: str) -> float:
        result = temp_re.match(temp)
        if result:
            return float(result.group(1))
        raise ValueError(f"Unable to parse temperature: {temp}")

    return [parse_temp(t) for t in header_row[1:]]


def _parse_duration(d: str) -> timedelta:
    splitted = d.split(":")
    if len(splitted) != 2:
        raise ValueError(f"Unable to parse duration: {d}")
    return timedelta(minutes=int(splitted[0]), seconds=int(splitted[1]))


def _evaluator(
    temperatures: List[float], durations: List[timedelta]
) -> Callable[[float], timedelta]:
    temp_durations = list(zip(temperatures, durations))

    def evaluate(temperature: float) -> timedelta:
        if temperature < temp_durations[0][0]:
            raise UserError("Too cold")
        if temperature > temp_durations[-1][0]:
            raise UserError("Too hot")

        last_t, last_d = temp_durations[0]
        for t, d in temp_durations[1:]:
            if last_t <= temperature and temperature < t:
                # We're there
                # Convert to seconds, as timedelta only seem to support integer mutiplications
                last_secs = last_d.total_seconds()
                secs = d.total_seconds()
                weighted = (
                    (temperature - last_t) * secs + (t - temperature) * last_secs
                ) / (t - last_t)
                return timedelta(seconds=weighted)
            last_t = t
            last_d = d

        # Edge case: exactly at the maximum
        return temp_durations[-1][1]

    return evaluate


def _read_chart_letter(csv_filename: str) -> Dict[str, Callable[[float], timedelta]]:
    durations_map = {}

    with open(csv_filename, newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        first_line = True
        temperatures: List[float] = []

        for row in reader:
            if first_line:
                first_line = False
                temperatures = _parse_temperatures_header(row)
                continue

            chart_letter = row[0]
            durations = [_parse_duration(d) for d in row[1:]]
            durations_map[chart_letter] = _evaluator(temperatures, durations)

    return durations_map


class DevelopmentTime:
    """A collection of film development times."""

    def __init__(self, film_csv_file: str, dev_times_csv_file) -> None:
        durations_map = _read_chart_letter(dev_times_csv_file)

        by_name: Dict[str, FilmDetails] = {}
        by_dx_number: Dict[str, FilmDetails] = {}

        for fd in _read_films(film_csv_file, durations_map):
            by_name[str(fd)] = fd
            if fd.dx_number:
                # Remove the last digit, which is the number of exposures
                by_dx_number[fd.dx_number[:5]] = fd

        self.by_name = by_name
        self.by_dx_number = by_dx_number

    def for_film(self, film_name: str) -> FilmDetails:
        """Return the film details for the given film name."""
        return self.by_name[film_name]

    def for_dx_number(self, dx_number: str) -> Optional[FilmDetails]:
        """Return the film details for the given DX number."""
        # Remove the last digit, which is the number of exposures
        return self.by_dx_number.get(dx_number[:5])
