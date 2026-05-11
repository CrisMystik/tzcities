import csv
from dataclasses import dataclass
from io import TextIOWrapper
import json
import os
import requests
import sys
from typing import Any
from zipfile import ZipFile

@dataclass
class GeoName:
    geoname_id: int
    name: str
    ascii_name: str
    alternate_names: list[str]
    latitude: float
    longitude: float
    feature_class: str
    feature_code: str
    country_code: str
    alternate_country_codes: list[str]
    admin1_code: str
    admin2_code: str
    admin3_code: str
    admin4_code: str
    population: int
    elevation: int
    dem: int
    timezone: str
    modification_date: str

@dataclass
class AlternateName:
    alternatename_id: int
    geoname_id: int
    iso_language: str
    alternate_name: str
    is_preferred_name: bool
    is_short_name: bool
    is_colloquial: bool
    is_historic: bool
    from_period: str
    to_period: str

@dataclass
class TimeZone:
    name: str
    country_code: str
    cities_geoname_id: list[int]

def download_file(url: str, path: str) -> None:
    r = requests.get(url)
    with open(path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=128):
            f.write(chunk)

must_refresh = '-r' in sys.argv

if must_refresh or not os.path.isfile('cities15000.zip'):
    download_file(
        'https://download.geonames.org/export/dump/cities15000.zip', 'cities15000.zip'
    )

if must_refresh or not os.path.isfile('alternateNamesV2.zip'):
    download_file(
        'https://download.geonames.org/export/dump/alternateNamesV2.zip', 'alternateNamesV2.zip'
    )

PSEUDO_LANGUAGE_CODES = {
    'post', 'icao', 'iata', 'faac', 'tcid',
    'abbr', 'link', 'phone', 'piny', 'wkdt',
    'unlc', 'nuts', 'lauc', ''
}

timezones: dict[str, TimeZone] = {}
cities: dict[int, GeoName] = {}
cities_alternate_names: dict[int, dict[str, list[AlternateName]]] = {}
cities_archive = ZipFile('cities15000.zip', 'r')
alternate_names_archive = ZipFile('alternateNamesV2.zip', 'r')

with cities_archive.open('cities15000.txt', 'r') as cities_file_raw:
    with TextIOWrapper(cities_file_raw, encoding='utf-8', newline='') as cities_file:
        reader = csv.reader(cities_file, delimiter='\t')
        for row in reader:
            city = GeoName(
                geoname_id=int(row[0]),
                name=row[1],
                ascii_name=row[2],
                alternate_names=row[3].split(',') if row[3] else [],
                latitude=float(row[4]),
                longitude=float(row[5]),
                feature_class=row[6],
                feature_code=row[7],
                country_code=row[8],
                alternate_country_codes=row[9].split(','),
                admin1_code=row[10],
                admin2_code=row[11],
                admin3_code=row[12],
                admin4_code=row[13],
                population=int(row[14]),
                elevation=int(row[15]) if row[15] else 0,
                dem=int(row[16]),
                timezone=row[17],
                modification_date=row[18]
            )
            cities[city.geoname_id] = city
            if city.timezone not in timezones:
                timezones[city.timezone] = TimeZone(city.timezone, city.country_code, [])
            timezones[city.timezone].cities_geoname_id.append(city.geoname_id)

with alternate_names_archive.open('alternateNamesV2.txt', 'r') as alternate_file_raw:
    with TextIOWrapper(alternate_file_raw, encoding='utf-8', newline='') as alternate_file:
        reader = csv.reader(alternate_file, delimiter='\t')
        for row in reader:
            geoname_id = int(row[1])
            if geoname_id not in cities:
                continue
            iso_language = row[2]
            if iso_language in PSEUDO_LANGUAGE_CODES:
                continue
            if geoname_id not in cities_alternate_names:
                cities_alternate_names[geoname_id] = {}
            if iso_language not in cities_alternate_names[geoname_id]:
                cities_alternate_names[geoname_id][iso_language] = []
            alt_name = AlternateName(
                alternatename_id=int(row[0]),
                geoname_id=geoname_id,
                iso_language=iso_language,
                alternate_name=row[3],
                is_preferred_name=row[4].strip() == '1',
                is_short_name=row[5].strip() == '1',
                is_colloquial=row[6].strip() == '1',
                is_historic=row[7].strip() == '1',
                from_period=row[8],
                to_period=row[9]
            )
            cities_alternate_names[geoname_id][iso_language].append(alt_name)

json_result: list[dict[str, Any]] = []
for timezone in timezones.values():
    tres: dict[str, Any] = {
        'name': timezone.name,
        'country_code': timezone.country_code,
        'cities': []
    }
    allowed_cities_ids = sorted(
        timezone.cities_geoname_id, key=lambda i: cities[i].population, reverse=True
    )[:4]
    for city_geoname_id in allowed_cities_ids:
        city = cities[city_geoname_id]
        cres: dict[str, Any] = {
            'name': city.name,
            'language_names': {}
        }
        if city_geoname_id in cities_alternate_names:
            for alternate_langcode in cities_alternate_names[city_geoname_id].keys():
                alternates = sorted([
                    a for a in cities_alternate_names[city_geoname_id][alternate_langcode]
                    if not (a.is_colloquial or a.is_historic or a.is_short_name)
                ], key=lambda a: a.is_preferred_name, reverse=True)
                if alternates:
                    cres['language_names'][alternate_langcode] = alternates[0].alternate_name
        tres['cities'].append(cres)

    json_result.append(tres)

with open('result.json', 'w', encoding='utf-8') as f:
    json.dump(json_result, f, ensure_ascii=False, indent=4)

with open('result.min.json', 'w', encoding='utf-8') as f:
    json.dump(json_result, f, indent=None, separators=(',', ':'))
