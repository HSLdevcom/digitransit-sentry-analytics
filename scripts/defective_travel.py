import requests
import pprint
import re
import datetime
import dateutil.tz as tz
import os
import cPickle
from urlparse import urlparse,parse_qs

#TODO fix this file

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


exclude_sites = ('localhost','dev.','127.0.0.1','beta.','foli.fi','pilot1', 'turku.')

last_url = None
if not os.path.exists('results_defective.dat'):
	events = []
	url = os.environ['SENTRY_BASE_URL'] # TODO add env variable for the issue number
	for i in xrange(100):
		print i,url,
		r = requests.get(url,headers={'Authorization':'Bearer %s' % os.environ['SENTRY_TOKEN']})

		links = parseSentryLinks(r.headers['link'])
		data = r.json()
		print data[0]['dateCreated'],data[-1]['dateCreated']

		for e in data:
			eventdt = datetime.datetime.strptime(e['dateCreated'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=tz.tzutc())


			try:
				events.append({
					'created':eventdt,
					'msg':e['message']
					})
			except KeyError as err:
				print err
				continue

		url = links['next']['url']

		if url == last_url:
			break

		last_url = url

		if not links['next']['results']:
			break



	f = open('results_defective.dat','wb')
	cPickle.dump(events,f,-1)
	f.close()
else:
	f = open('results_defective.dat','rb')
	events = cPickle.load(f)
	f.close()


def parseOTPPlace(p):
	p = p.replace('%3A%3A','::')
	p = p.replace('%2C',',')
	ret = dict(zip(('name','coords'),p.split('::')))
	if not 'coords' in ret:
		return None

	try:
		ret['lat'],ret['lon'] = map(float,ret['coords'].split(','))
	except ValueError:
		return None

	return ret





i = 0
fromto_identical = 0
too_old_time = 0
problem_patterns = {}

for e in events:

	e['created'] = e['created'].astimezone(tz.tzlocal())

	msgparts = re.search(r'Defective traversal flagged on edge PatternDwell\(org.opentripplanner.routing.edgetype.PatternDwell:(?P<edge>[\d]*?) \(<(?P<pattern1>.*?)_(.*?)lat,lng=(?P<latlon1>[\d,.]*?)> -> <(?P<pattern2>.*?)_(.*?)lat,lng=(?P<latlon2>[\d,.]*?)>',e['msg'])
	if not msgparts:
		print e['msg']
		continue
	msginfo = msgparts.groupdict()

	p1 = msginfo['pattern1']
	if not p1 in problem_patterns:
		problem_patterns[p1] = {'count':0,'mindate':e['created'],'maxdate':e['created'],'pattern':p1,'latlon':msginfo['latlon1']}

	problem_patterns[p1]['count'] += 1

	if e['created'] < problem_patterns[p1]['mindate']:
		problem_patterns[p1]['mindate'] = e['created']
	
	if e['created'] > problem_patterns[p1]['maxdate']:
		problem_patterns[p1]['maxdate'] = e['created']

	
	i+=1




print 'unknown errors',i

of = open('report_defective.html','w+')
of.write('<html><style>td,th { font-size: 12px; font-family: arial;}</style><table border="1">')

for pp in problem_patterns.itervalues():
	print pp['pattern']
	r = requests.get('https://api.digitransit.fi/routing/v1/routers/finland/index/patterns/%(pattern)s/trips' % pp)
	if r.content == 'FOUR ZERO FOUR':
		pp['trips'] = 'Old pattern'
	else:
		try:
			trips = r.json()
		except:

			print repr(r.content)
			raise

		pp['trips'] = '<br/>'.join((t['id'] for t in trips))
	of.write('<tr><td>%(maxdate)s</td><td>%(mindate)s</td><td>%(count)s</td><td>%(pattern)s</td><td>%(trips)s</td><td>%(latlon)s</td></tr>' % pp)
	print 'done'


of.write('</table></html>')
print 'problem patterns',len(problem_patterns)