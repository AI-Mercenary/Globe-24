"""Static file server + small proxy for feeds that block browser (CORS) requests.

Usage:  python serve.py [port]      (default 5173)
Routes:
  /api/aircraft   OpenSky Network global ADS-B state vectors (cached 60 s)
  /api/tle?...    CelesTrak element sets, cached on disk 2 h, mirror fallback
"""
import http.server, json, sys, time, urllib.request, os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', 5173))
ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = {}  # url -> (time, status, body)
TTL = 60


def fetch(url):
    hit = CACHE.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1], hit[2]
    req = urllib.request.Request(url, headers={'User-Agent': 'global-ops-globe/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            CACHE[url] = (time.time(), 200, body)
            return 200, body
    except urllib.error.HTTPError as e:
        if hit:                      # rate-limited: serve the last good snapshot
            return hit[1], hit[2]
        return e.code, json.dumps({'error': f'upstream {e.code}'}).encode()
    except Exception as e:
        if hit:
            return hit[1], hit[2]
        return 502, json.dumps({'error': str(e)}).encode()


TLE_DIR = os.path.join(ROOT, '.tle-cache')
TLE_TTL = 2 * 3600          # CelesTrak asks clients not to re-download a set within 2 h


def mirror_tle(query):
    """Fallback: tle.ivanstanojevic.me re-publishes the same NORAD/CelesTrak element sets."""
    url = 'https://tle.ivanstanojevic.me/api/tle/25544' if query == 'CATNR=25544' else \
          'https://tle.ivanstanojevic.me/api/tle?page-size=100&sort=popularity&sort-dir=desc'
    req = urllib.request.Request(url, headers={'User-Agent': 'global-ops-globe/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.loads(r.read())
    sats = [j] if 'line1' in j else j.get('member', [])
    return '\n'.join(f"{s['name']}\n{s['line1']}\n{s['line2']}" for s in sats).encode()


def get_tle(query):
    os.makedirs(TLE_DIR, exist_ok=True)
    path = os.path.join(TLE_DIR, query.replace('=', '_') + '.txt')
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < TLE_TTL
    if fresh:
        return open(path, 'rb').read(), 'cache'
    try:
        req = urllib.request.Request(f'https://celestrak.org/NORAD/elements/gp.php?{query}&FORMAT=tle',
                                     headers={'User-Agent': 'global-ops-globe/1.0'})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
        if b'\n1 ' in body or body.startswith(b'1 '):
            open(path, 'wb').write(body)
            return body, 'celestrak'
    except Exception:
        pass
    if os.path.exists(path):                      # stale but genuine element sets
        return open(path, 'rb').read(), 'cache-stale'
    try:
        body = mirror_tle(query)
        if body:
            open(path, 'wb').write(body)
            os.utime(path, (time.time() - TLE_TTL + 900,) * 2)   # retry CelesTrak in 15 min
            return body, 'mirror'
    except Exception:
        pass
    return None, 'unavailable'


# whitelisted upstream feeds that don't send CORS headers (id -> (url, cache seconds))
FEEDS = {
    'gdacs':    ('https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP', 300),
    'tsu_ntwc': ('https://www.tsunami.gov/events/xml/PAAQAtom.xml', 120),
    'tsu_ptwc': ('https://www.tsunami.gov/events/xml/PHEBAtom.xml', 120),
    'nhc':      ('https://www.nhc.noaa.gov/CurrentStorms.json', 300),
}
FIRMS = 'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{src}/world/1'


def cached(url, ttl):
    hit = CACHE.get(url)
    if hit and time.time() - hit[0] < ttl:
        return hit[1], hit[2]
    req = urllib.request.Request(url, headers={'User-Agent': 'global-ops-globe/1.0 (research dashboard)'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        CACHE[url] = (time.time(), 200, body)
        return 200, body
    except urllib.error.HTTPError as e:
        return (hit[1], hit[2]) if hit else (e.code, f'upstream {e.code}'.encode())
    except Exception as e:
        return (hit[1], hit[2]) if hit else (502, str(e).encode())


# per-aircraft lookups (id is validated before use)
AIRCRAFT = {
    'acinfo':  ('https://api.adsbdb.com/v0/aircraft/{id}', 86400),
    'route':   ('https://api.adsbdb.com/v0/callsign/{id}', 3600),
    'acphoto': ('https://api.planespotters.net/pub/photos/hex/{id}', 86400),
    'track':   ('https://opensky-network.org/api/tracks/all?icao24={id}&time=0', 60),
    'pop':     ('https://api.worldbank.org/v2/country/{id}/indicator/SP.POP.TOTL?format=json&mrnev=1', 86400),
}
AIRPORTS_CSV = 'https://davidmegginson.github.io/ourairports-data/airports.csv'


def airports_json():
    """Large airports from OurAirports, filtered once and cached on disk."""
    path = os.path.join(TLE_DIR, 'airports.json')
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 7 * 86400:
        return open(path, 'rb').read()
    import csv, io
    req = urllib.request.Request(AIRPORTS_CSV, headers={'User-Agent': 'global-ops-globe/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = csv.DictReader(io.StringIO(r.read().decode('utf-8')))
        out = [[a['ident'], a['iata_code'], a['name'], round(float(a['latitude_deg']), 4), round(float(a['longitude_deg']), 4),
                int(float(a['elevation_ft'] or 0)), a['iso_country'], a['municipality']]
               for a in rows if a['type'] == 'large_airport' and a['scheduled_service'] == 'yes']
    body = json.dumps(out).encode()
    os.makedirs(TLE_DIR, exist_ok=True)
    open(path, 'wb').write(body)
    return body


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def do_GET(self):
        if self.path.startswith('/api/aircraft'):
            status, body = fetch('https://opensky-network.org/api/states/all')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        parts = self.path.split('?')[0].strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'api' and parts[1] in AIRCRAFT:
            ident = ''.join(c for c in parts[2] if c.isalnum())[:10]
            if not ident:
                self.send_error(400); return
            status, body = cached(AIRCRAFT[parts[1]][0].format(id=ident), AIRCRAFT[parts[1]][1])
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith('/api/airports'):
            try:
                body, status = airports_json(), 200
            except Exception as e:
                body, status = json.dumps({'error': str(e)}).encode(), 502
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith('/api/feed/') or self.path.startswith('/api/firms?'):
            from urllib.parse import urlparse, parse_qs
            u = urlparse(self.path)
            if u.path.startswith('/api/firms'):
                q = parse_qs(u.query)
                key = ''.join(c for c in q.get('key', [''])[0] if c.isalnum())
                src = q.get('src', ['VIIRS_NOAA20_NRT'])[0]
                if not key or src not in ('VIIRS_SNPP_NRT', 'VIIRS_NOAA20_NRT', 'VIIRS_NOAA21_NRT', 'MODIS_NRT'):
                    self.send_error(400); return
                status, body = cached(FIRMS.format(key=key, src=src), 600)
                ctype = 'text/csv'
            else:
                fid = u.path.rsplit('/', 1)[1]
                if fid not in FEEDS:
                    self.send_error(404); return
                status, body = cached(*FEEDS[fid])
                ctype = 'application/json' if FEEDS[fid][0].endswith(('json', 'EVENTS4APP')) else 'application/xml'
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith('/api/tle?'):
            q = self.path.split('?', 1)[1]
            if q not in ('GROUP=visual', 'CATNR=25544', 'GROUP=stations', 'GROUP=weather', 'GROUP=gps-ops', 'GROUP=starlink', 'GROUP=geo', 'GROUP=military', 'GROUP=resource'):
                self.send_error(400); return
            body, origin = get_tle(q)
            self.send_response(200 if body else 503)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('X-TLE-Source', origin)
            self.end_headers()
            self.wfile.write(body or b'unavailable')
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        if '/api/' in (args[0] if args else ''):
            super().log_message(fmt, *args)


if __name__ == '__main__':
    print(f'Global Ops on http://localhost:{PORT}')
    http.server.ThreadingHTTPServer(('', PORT), Handler).serve_forever()
