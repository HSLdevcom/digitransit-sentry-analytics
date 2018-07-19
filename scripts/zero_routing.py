import requests
import pprint
import re
import datetime
import dateutil.tz as tz
import os
import pickle
import random
import unicodecsv
import numpy as np
import utm
from sklearn.cluster import DBSCAN
from urllib.parse import urlparse, parse_qs

def parseSentryLink(link):
    url = link.pop(0).strip('<>')
    ret = {'url':url}
    for l in link:
        ma = re.search(r'(.*?)="(.*?)"',l)
        k,v = ma.group(1), ma.group(2)

        ret[k] = v

    ret['results'] = ret['results'] == 'true'
    return ret

def parseSentryLinks(link):
    links = ([f.strip() for f in l.split(';')] for l in link.split(','))

    links = [parseSentryLink(l) for l in links]

    return {l['rel']: l for l in links}

def clusterEndpoints(orig_endpoints, name_prefix, eps=2500, min_samples=2, return_outliers=True):
    coords = []
    coordhits = []
    invalid_coordinates = 0	
    for coord, hits in orig_endpoints.items():
        lat = coord[0]
        lon = coord[1]

        utm35_coordinates = utm.from_latlon(lat, lon, 35)
        x = utm35_coordinates[0]
        y = utm35_coordinates[1]

        x += random.uniform(-50, 50)
        y += random.uniform(-50, 50)

        coords.append((x, y))
        coordhits.append((hits,))

    coords = np.array(coords)
    coordhits = np.array(coordhits)

    db = DBSCAN(eps=eps, min_samples=min_samples, algorithm='auto', metric='euclidean').fit(coords)
    coords = np.hstack((coords,coordhits))
    cluster_labels = db.labels_
    n_clusters = len(set(cluster_labels))
    clusters = (coords[cluster_labels == n] for n in range(-1, n_clusters))

    outliers = next(clusters)

    endpoints = []
    if return_outliers:
        for o in outliers:
            if np.isnan(o[0]):
                continue
            try:
                lat, lon = utm.to_latlon(o[0], o[1], 35, 'N')
                endpoints.append({'name': '%s_outlier_%d' %  (name_prefix, len(endpoints)), 'lon': lon, 'lat': lat,'hits':o[2]})
            except utm.error.OutOfRangeError:
                invalid_coordinates += 1

    for c in clusters:
        if len(c) == 0:
            continue
        cp = np.nanmean(c, axis=0)
        hitsum = np.sum(c[:,2])
        if np.isnan(cp[0]):
            continue
        try:
            lat, lon = utm.to_latlon(cp[0], cp[1], 35, 'N')

            endpoints.append({'name': '%s_cluster_%d' % (name_prefix, len(endpoints)), 'lon': lon, 'lat': lat,'hits':hitsum})
        except utm.error.OutOfRangeError:
                invalid_coordinates += 1

    return (endpoints, invalid_coordinates)

last_url = None
if os.environ.get('DISABLE_CACHE') != 'true' or not os.path.exists('../results.dat'):
    events = []
    url = os.environ['SENTRY_URL']
    for i in range(100):
        print(i,url,)
        r = requests.get(url,headers={'Authorization':'Bearer %s' % os.environ['SENTRY_TOKEN']})

        links = parseSentryLinks(r.headers['link'])
        data = r.json()
        for e in data:
            ctx = e['context']

            eventdt = datetime.datetime.strptime(e['dateCreated'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=tz.tzutc()).astimezone(tz=None)
            searchdt = datetime.datetime.fromtimestamp(float(ctx['unixTime'])/1000).replace(tzinfo=tz.gettz('Europe/Helsinki'))
            from_coordinates = tuple(map(lambda x: None if x == 'null' or x == '' else float(x), ctx['from'][25:][:-1].split(',')))
            to_coordinates = tuple(map(lambda x: None if x == 'null' or x == '' else float(x), ctx['to'][25:][:-1].split(',')))
            events.append({
                'created': eventdt,
                'time': searchdt,
                'zones': ctx['zoneids'],
                'modes': ctx['modes'][14:][:-1].replace(" ", "").split(','),
                'from': from_coordinates,
                'to': to_coordinates,
                'router': ctx['routerId'],
                'configuration': (
                    ctx['arriveBy'],
                    ctx['maxTransfers'],
                    ctx['maxWalkDistance'],
                    ctx['minTransferTime'],
                    ctx['stairsReluctance'],
                    ctx['transferPenalty'],
                    ctx['waitReluctance'],
                    ctx['walkOnStreetReluctance'],
                    ctx['walkReluctance'],
                    ctx['walkSpeed']
                )
            })

        if not links['next']['results']:
            continue

        url = links['next']['url']

        if url == last_url:
            break

        last_url = url

    if os.environ.get('DISABLE_CACHE') != 'true':
        f = open('../results.dat','wb')
        pickle.dump(events,f,-1)
        f.close()
else:
    f = open('../results.dat','rb')
    events = pickle.load(f)
    f.close()


of = open('../reports/report.html','w+')
of.write('<html><head><link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.10.19/css/jquery.dataTables.css">')
of.write('<script src="https://ajax.googleapis.com/ajax/libs/jquery/3.3.1/jquery.min.js">')
of.write('</script><script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.10.19/js/jquery.dataTables.js"></script></head>')
of.write('<body><style>td,th { font-size: 12px; font-family: arial;} .dataTables_wrapper { margin-bottom: 20px !important; }</style>')
of.write('<script>$(document).ready( function () { $(\'#datatable\').DataTable(); $(\'#conftable\').DataTable(); $(\'#clustertable\').DataTable();} );</script>')
of.write('<h2>Error events after filtering <a href=filtered_coordinates.csv>CSV coordinates</a></h2>')
of.write('<table border="1" id="datatable">')
of.write('<thead><tr><th>router</th><th>time</th><th>created</th><th>from</th><th>to</th><th>configuration index</th><th>link</th></tr></thead>\n<tbody>')
i = 0
fromto_closeby = 0
too_old_time = 0
fromto_null = 0
from_null = 0
to_null = 0

configurations = {}

hsl_origins = {}
hsl_destinations = {}
waltti_origins = {}
waltti_destinations = {}
finland_origins = {}
finland_destinations = {}

for e in events:

    if e['from'][0] is None and e['to'][0] is None:
        fromto_null += 1
        continue
    elif e['from'][0] is None:
        from_null += 1
        continue
    elif e['to'][0] is None:
        to_null += 1
        continue

    known_error = False
    utm_from = utm.from_latlon(e['from'][0], e['from'][1], 35)
    utm_to = utm.from_latlon(e['to'][0], e['to'][1], 35)
    # Filter out errors where from and to differ by at most by roughly 30 meters
    if abs(utm_from[0] - utm_to[0]) + abs(utm_from[1] - utm_to[1]) < 30:
        fromto_closeby += 1
        known_error = True

    # Filter out errors where user searches 1 day in the past from when error was generated
    if e['time']-e['created'] < datetime.timedelta(days=-1):
        too_old_time += 1
        known_error = True

    # Filter out errors when user has ticket restrictions
    if e['zones'] != 'All zones allowed':
        continue

    # Filter out errors when bicycle, bus or tram is not selected as available mode
    if 'BICYCLE' not in e['modes'] and 'BUS' not in e['modes'] and 'TRAM' not in e['modes']:
        continue

    if known_error:
        continue

    link = ''
    if e['router'] == 'hsl':
        link = 'https://www.reittiopas.fi/reitti/from::%f%%2C%f/to::%f%%2C%f' % (e['from'][0], e['from'][1], e['to'][0], e['to'][1])
        if e['from'] in hsl_origins:
            hsl_origins[e['from']] += 1
        else:
            hsl_origins[e['from']] = 1

        if e['to'] in hsl_destinations:
            hsl_destinations[e['to']] += 1
        else:
            hsl_destinations[e['to']] = 1
    elif e['router'] == 'waltti':
        link = 'https://reittiopas.foli.fi/reitti/from::%f%%2C%f/to::%f%%2C%f' % (e['from'][0], e['from'][1], e['to'][0], e['to'][1])
        if e['from'] in waltti_origins:
            waltti_origins[e['from']] += 1
        else:
            waltti_origins[e['from']] = 1

        if e['to'] in waltti_destinations:
            waltti_destinations[e['to']] += 1
        else:
            waltti_destinations[e['to']] = 1
    else:
        link = 'https://opas.matka.fi/reitti/from::%f%%2C%f/to::%f%%2C%f' % (e['from'][0], e['from'][1], e['to'][0], e['to'][1])
        if e['from'] in finland_origins:
            finland_origins[e['from']] += 1
        else:
            finland_origins[e['from']] = 1

        if e['to'] in finland_destinations:
            finland_destinations[e['to']] += 1
        else:
            finland_destinations[e['to']] = 1

    link_element = '<a href="%s"/>%s</a>' % (link, link)

    if e['configuration'] in configurations:
        configurations[e['configuration']][1] += 1
        e['confIndex'] = configurations[e['configuration']][0]
    else:
        e['confIndex'] = len(configurations.keys())
        configurations[e['configuration']] = [e['confIndex'], 1]
    of.write('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%s</td></tr>\n' \
        % (e['router'], e['time'], e['created'], e['from'], e['to'], e['confIndex'], link_element))
    i+=1

of.write('</tbody></table>')

of.write('<h2>Configuration mapping</h2>')
of.write('<table border="1" id="conftable">')
of.write('<thead><tr><th>configuration index</th><th>count</th><th>arriveBy</th><th>maxTransfers</th><th>maxWalkDistance</th>')
of.write('<th>minTransferTime</th><th>stairsReluctance</th><th>transferPenalty</th><th>waitReluctance</th>')
of.write('<th>walkOnStreetReluctance</th><th>walkReluctance</th><th>walkSpeed</th></thead>')
of.write('<tbody>')
for key, value in configurations.items():
    of.write('<tr><td>%d</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n'
        % (value[0], value[1], key[0], key[1], key[2], key[3], key[4], key[5], key[6], key[7], key[8], key[9]))
of.write('</tbody></table>')

hsl_clustered_origins, hsl_origins_invalid = clusterEndpoints(hsl_origins, 'hsl_origin')
hsl_clustered_destinations, hsl_destinations_invalid = clusterEndpoints(hsl_destinations, 'hsl_destination')

waltti_clustered_origins, waltti_origins_invalid = clusterEndpoints(waltti_origins, 'waltti_origin')
waltti_clustered_destinations, waltti_destinations_invalid = clusterEndpoints(waltti_destinations, 'waltti_destination')

finland_clustered_origins, finland_origins_invalid = clusterEndpoints(finland_origins, 'finland_origin')
finland_clustered_destinations, finland_destinations_invalid = clusterEndpoints(finland_destinations, 'finland_destination')

combined_clusters = hsl_clustered_origins + hsl_clustered_destinations + waltti_clustered_origins \
    + waltti_clustered_destinations + finland_clustered_origins + finland_clustered_destinations
combined_invalid_coordinates = hsl_origins_invalid + hsl_destinations_invalid + waltti_origins_invalid \
    + waltti_destinations_invalid + finland_origins_invalid + finland_destinations_invalid

of.write('<h2>Coordinate clusters and outliers <a href=clusters_and_outliers.csv>CSV coordinates</a></h2>')
of.write('<table border="1" id="clustertable">')
of.write('<thead><tr><th>name</th><th>hits</th><th>lat</th><th>lon</th></thead>')
of.write('<tbody>')
for cluster in combined_clusters:
    of.write('<tr><td>%(name)s</td><td>%(hits)d</td><td>%(lat)f</td><td>%(lon)f</td></tr>\n' % cluster)
of.write('</tbody></table>')

of.write('<h2>Issue types</h2>')
of.write('<table border="1">')
of.write('<thead><tr><th>issue type</th><th>count</th></thead>')
of.write('<tbody>')
of.write('<tr><td>From and to are null</td><td>%d</td></tr>' %fromto_null)
of.write('<tr><td>From is null</td><td>%d</td></tr>' %from_null)
of.write('<tr><td>To is null</td><td>%d</td></tr>' %to_null)
of.write('<tr><td>From and to are really next to each other</td><td>%d</td></tr>' %fromto_closeby)
of.write('<tr><td>Coordinates are far away from finland</td><td>%d</td></tr>' %combined_invalid_coordinates)
of.write('<tr><td>Search time is too much in the past</td><td>%d</td></tr>' %too_old_time)
of.write('<tr><td>Unknown errors (these are included in the tables above)</td><td>%d</td></tr>' %i)

of.write('</tbody></table></body></html>')

of.close()

print('report.html updated')

f = open('../reports/clusters_and_outliers.csv', 'wb')
w = unicodecsv.writer(f, encoding='utf-8')
w.writerow(('name', 'hits', 'lon', 'lat'))

for cluster in combined_clusters:
    w.writerow((cluster['name'], cluster['hits'], cluster['lon'], cluster['lat']))

f.close()
print('clusters_and_outliers.csv updated')

f = open('../reports/filtered_coordinates.csv', 'wb')
w = unicodecsv.writer(f, encoding='utf-8')
w.writerow(('name', 'hits', 'lon', 'lat'))
i = 0
for coord, hits in hsl_origins.items():
    w.writerow(('hsl_origin_%d' %i, hits, coord[1], coord[0]))
    i += 1
i = 0
for coord, hits in hsl_destinations.items():
    w.writerow(('hsl_destination_%d' %i, hits, coord[1], coord[0]))
    i += 1
i = 0
for coord, hits in waltti_origins.items():
    w.writerow(('waltti_origin_%d' %i, hits, coord[1], coord[0]))
    i += 1
i = 0
for coord, hits in waltti_destinations.items():
    w.writerow(('waltti_destination_%d' %i, hits, coord[1], coord[0]))
    i += 1
i = 0
for coord, hits in finland_origins.items():
    w.writerow(('finland_origin_%d' %i, hits, coord[1], coord[0]))
    i += 1
i = 0
for coord, hits in finland_destinations.items():
    w.writerow(('finland_destination_%d' %i, hits, coord[1], coord[0]))
    i += 1
i = 0

f.close()
print('filtered_coordinates.csv updated')

