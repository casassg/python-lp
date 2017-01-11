#!/usr/bin/python3.5
import collections
import string
import sys
import xml.etree.ElementTree as ET
from itertools import islice
from math import radians, cos, sin, asin, sqrt
from pprint import pprint
from urllib import request
# Constants
import datetime

DATE_FORMAT = "%d/%m/%Y"

URL_ACTIVITATS = 'http://www.bcn.cat/tercerlloc/agenda_cultural.xml'
URL_APARCAMENTS = 'http://www.bcn.cat/tercerlloc/Aparcaments.xml'
URL_BICING = 'http://wservice.viabicing.cat/getstations.php?v=1'


# Load key argument
def load_arg(key):
    value = None
    if key in sys.argv:
        try:
            value = eval(sys.argv[sys.argv.index(key) + 1])
        except IndexError:
            sys.exit('argument for %s is not set properly' % key)
    return value


def parse_act_row(item):
    item = item[0]
    bd = item.find('begindate')
    ed = item.find('enddate')
    name = item.find('name')
    address_xml = item.find('addresses')
    hour = item.find('proxhour')
    lat = item.find('gmapx')
    long = item.find('gmapy')
    if not address_xml:
        return None
    barri = address_xml[0].find('barri')
    address = address_xml[0].find('address')
    if any(map(lambda x: x is None, [bd, ed, name, barri, address, hour, lat, long])):
        return None
    else:
        return {
            'begin': bd.text,
            'end': ed.text,
            'name': name.text,
            'barri': barri.text,
            'address': address.text,
            'hour': hour.text,
            'lat': lat.text,
            'long': long.text,
        }


def parse_acts(xml):
    root = ET.fromstring(xml)
    acts = map(parse_act_row, root.iter('row'))
    return acts


def parse_bicing_station(station):
    _id = station.find('id')
    lat = station.find('lat')
    long = station.find('long')
    street = station.find('street')
    bikes = station.find('bikes')
    slots = station.find('slots')
    if any(map(lambda x: x is None, [_id, street, lat, long, bikes, slots])):
        return None
    return {
        'id': _id.text,
        'lat': lat.text,
        'long': long.text,
        'street': street.text,
        'bikes': bikes.text,
        'slots': slots.text,
    }


def parse_bicing(xml):
    root = ET.fromstring(xml)
    stations = map(parse_bicing_station, root.iter('station'))
    # Returning a list because we will need to iterate this multiple times
    return list(filter(None, stations))


def request_xml(url):
    resp = request.urlopen(url)
    if resp.status != 200:
        sys.exit('Request to %s returned %s' % (resp.geturl(), resp.status))
    return resp.read()


def clean_word(word):
    table = collections.defaultdict(lambda: None)
    table.update({
        ord('à'): 'a',
        ord('á'): 'a',
        ord('è'): 'e',
        ord('é'): 'e',
        ord('í'): 'i',
        ord('ì'): 'i',
        ord('ó'): 'o',
        ord('ò'): 'o',
        ord('ú'): 'u',
        ord('ù'): 'u',
        ord(' '): ' ',
    })
    table.update(dict(zip(map(ord, string.ascii_uppercase), string.ascii_lowercase)))
    table.update(dict(zip(map(ord, string.ascii_lowercase), string.ascii_lowercase)))
    table.update(dict(zip(map(ord, string.digits), string.digits)))

    return word.translate(table, )


def create_filter_key(key):
    def filter_key(elem):
        if isinstance(key, str):
            return clean_word(key) in clean_word(elem['barri']) or \
                   clean_word(key) in clean_word(elem['name']) or \
                   clean_word(key) in clean_word(elem['address'])
        if isinstance(key, list):
            filters = map(create_filter_key, key)
            return all(map(lambda f: f(elem), filters))
        if isinstance(key, tuple):
            return any(map(lambda f: f(elem), map(create_filter_key, key)))
        return False

    return filter_key


def create_filter_date(date):
    def filter_date(elem):
        if isinstance(date, str):
            current = datetime.datetime.strptime(date, DATE_FORMAT)
            start = datetime.datetime.strptime(elem['begin'], DATE_FORMAT)
            end = datetime.datetime.strptime(elem['end'], DATE_FORMAT)
            return start <= current <= end
        if isinstance(date, list):
            filters = map(create_filter_date, date)
            return any(map(lambda f: f(elem), filters))
        if isinstance(date, tuple):
            current = datetime.datetime.strptime(date[0], DATE_FORMAT)
            o_prev = current + datetime.timedelta(date[1])
            o_post = current + datetime.timedelta(date[2])
            start = datetime.datetime.strptime(elem['begin'], DATE_FORMAT)
            end = datetime.datetime.strptime(elem['end'], DATE_FORMAT)
            return not (start > o_post or end < o_prev)
        return False

    return filter_date


def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    m = 6367 * 1000 * c
    return m


def distance(elem, station):
    if not elem or not station:
        return 0.0
    return haversine(station['long'], station['lat'], elem['long'], elem['lat'])


def create_stations_mapper(stations):
    def f(elem):
        def add_d(station):
            dist = distance(elem, station)
            station['d'] = dist

        current_st = map(add_d, stations)
        # current_st = filter(lambda x: distance(elem, x) <= 500, current_st)
        current_st = sorted(current_st, key=lambda x: distance(elem, x))
        elem['bicing_slots'] = list(islice(filter(lambda x: int(x['slots']) > 0, current_st), 5))
        elem['bicing_bikes'] = list(islice(filter(lambda x: int(x['bikes']) > 0, current_st), 5))
        return elem

    return f


def main():
    key = load_arg('--key')
    date = load_arg('--date')
    acts = parse_acts(request_xml(URL_ACTIVITATS))
    # Remove None
    acts = filter(None, acts)
    if key:
        acts = filter(create_filter_key(key), acts)
    if date:
        acts = filter(create_filter_date(date), acts)

    stations = parse_bicing(request_xml(URL_BICING))
    acts = map(create_stations_mapper(stations), acts)
    pprint(list(acts))


if __name__ == '__main__':
    main()
