import csv
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class FilmDetails:
    brand: str
    film_type: str
    dx_number: str
    evaluator: Callable[[float], timedelta]

    def __str__(self) -> str:
        return f"{self.brand} {self.film_type}"
    
    def development_time(self, temp: float) -> timedelta:
        return self.evaluator(temp)


def _read_films(csv_filename: str, durations_map: Dict[str, Callable[[float], timedelta]]):
    with open(csv_filename, newline='') as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            brand = row['Brand']
            film_type = row['Film Type']
            dx_number = row['DX Number']
            chart_letter = row['Chart Letter']
            evaluator = durations_map[chart_letter]

            yield FilmDetails(
                brand=brand,
                film_type=film_type,
                dx_number=dx_number,
                evaluator=evaluator)


def _parse_temperatures_header(header_row) -> List[float]:
    if header_row[0] != 'Chart Letter':
        raise Exception("Expected: Chart Letter")

    temp_re = re.compile('^([+-]?\\d*[.,]?\\d*)°C$')

    def parse_temp(temp: str) -> float:
        result = temp_re.match(temp)
        if result:
            return float(result.group(1))
        raise Exception("Unable to parse temperature: " + temp)

    return [parse_temp(t) for t in header_row[1:]]


def _parse_duration(d: str) -> timedelta:
    splitted = d.split(':')
    if len(splitted) != 2:
        raise Exception("Unable to parse duration: " + d)
    return timedelta(minutes=int(splitted[0]), seconds=int(splitted[1]))


def _evaluator(temperatures: List[float], durations: List[timedelta]) -> Callable[[float], timedelta]:
    temp_durations = list(zip(temperatures, durations))

    def eval(temperature: float) -> timedelta:
        if temperature < temp_durations[0][0]:
            raise Exception("Too cold")
        if temperature > temp_durations[-1][0]:
            raise Exception("Too hot")

        last_t, last_d = temp_durations[0]
        for t, d in temp_durations[1:]:
            if last_t <= temperature and temperature < t:
                # We're there
                return ((temperature - last_t) * d + (t - temperature) * last_d) / (t - last_t)
            last_t = t
            last_d = d
        
        # Edge case: exactly at the maximum
        return temp_durations[-1][1]

    return eval


def _read_chart_letter(csv_filename: str) -> Dict[str, Callable[[float], timedelta]]:
    durations_map = {}

    with open(csv_filename, newline='') as csv_file:
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
        return self.by_name[film_name]

    def for_dx_number(self, dx_number: str) -> Optional[FilmDetails]:
        # Remove the last digit, which is the number of exposures
        return self.by_dx_number.get(dx_number[:5])
