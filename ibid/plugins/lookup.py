from urllib2 import urlopen, Request
from urllib import urlencode, quote
from time import time
from datetime import datetime
from simplejson import loads
import re

import feedparser
from BeautifulSoup import BeautifulSoup

from ibid.plugins import Processor, match, handler
from ibid.config import Option
from ibid.utils import ago, decode_htmlentities

help = {}

help['bash'] = u'Retrieve quotes from bash.org.'
class Bash(Processor):
    u"bash[.org] (random|<number>)"

    feature = 'bash'

    @match(r'^bash(?:\.org)?\s+(random|\d+)$')
    def bash(self, event, quote):
        f = urlopen('http://bash.org/?%s' % quote.lower())
        soup = BeautifulSoup(f.read(), convertEntities=BeautifulSoup.HTML_ENTITIES)
        f.close()

        if quote.lower() == "random":
            number = u"".join(soup.find('p', attrs={'class': 'quote'}).find('b').contents)
            event.addresponse(u'%s:', number)

        quote = soup.find('p', attrs={'class': 'qt'})
        if not quote:
            event.addresponse(u"There's no such quote, but if you keep talking like that maybe there will be")
        else:
            for line in quote.contents:
                if str(line) != '<br />':
                    event.addresponse(u'%s', line.strip())

help['lastfm'] = u'Lists the tracks last listened to by the specified user.'
class LastFm(Processor):
    u"last.fm for <username>"

    feature = "lastfm"

    @match(r'^last\.?fm\s+for\s+(\S+?)\s*$')
    def listsongs(self, event, username):
        songs = feedparser.parse('http://ws.audioscrobbler.com/1.0/user/%s/recenttracks.rss?%s' % (username, time()))
        if songs['bozo']:
            event.addresponse(u'No such user')
        else:
            event.addresponse(u'%s', u', '.join(u'%s (%s ago)' % (e.title, ago(datetime.utcnow() - datetime.strptime(e.updated, '%a, %d %b %Y %H:%M:%S +0000'), 1)) for e in songs['entries']))

help['lotto'] = u"Gets the latest lotto results from the South African National Lottery."
class Lotto(Processor):
    u"""lotto"""

    feature = 'lotto'
    
    za_url = 'http://www.nationallottery.co.za/'
    za_re = re.compile(r'images/balls/ball_(\d+).gif')
    
    @match(r'lotto(\s+for\s+south\s+africa)?')
    def za(self, event, za):
        try:
            f = urlopen(self.za_url)
        except Exception, e:
            event.addresponse(u'Something went wrong getting to the Lotto site')
            return
        
        s = "".join(f)
        f.close()
        
        balls = self.za_re.findall(s)
        
        if len(balls) != 14:
            event.addresponse(u'I expected to get %(expected)s balls, but found %(found)s. They were: %(balls)s', {
                'expected': 14,
                'found': len(balls),
                'balls': u', '.join(balls),
            })
            return
        
        event.addresponse(u'Latest lotto results for South Africa, '
            u'Lotto: %(lottoballs)s (Bonus: %(lottobonus)s), Lotto Plus: %(plusballs)s (Bonus: %(plusbonus)s)', {
            'lottoballs': u" ".join(balls[:6]),
            'lottobonus': balls[6],
            'plusballs':  u" ".join(balls[7:13]),
            'plusbonus':  balls[13],
        })

help['fml'] = u'Retrieves quotes from fmylife.com.'
class FMyLife(Processor):
    u"""fml (<number>|random)"""

    feature = "fml"

    def remote_get(self, id):
        f = urlopen('http://www.fmylife.com/' + str(id))
        soup = BeautifulSoup(f.read())
        f.close()

        quote = soup.find('div', id='wrapper').div.p
        return quote and u'"%s"' % (quote.contents[0],) or None

    @match(r'^(?:fml\s+|http://www\.fmylife\.com/\S+/)(\d+|random)$')
    def fml(self, event, id):
        quote = self.remote_get(id)
        if quote:
            event.addresponse(u'%s', quote)
        else:
            event.addresponse(u'No such quote')

help["microblog"] = u"Looks up messages on microblogging services like twitter and identica."
class Twitter(Processor):
    u"""latest (tweet|identica) from <name>
    (tweet|identica) <number>"""

    feature = "microblog"

    default = { 'twitter': 'http://twitter.com/',
                'tweet': 'http://twitter.com/',
                'identica': 'http://identi.ca/api/',
                'identi.ca': 'http://identi.ca/api/',
              }
    services = Option('services', 'Micro blogging services', default)

    def setup(self):
        self.update.im_func.pattern = re.compile(r'^(%s)\s+(\d+)$' % ('|'.join(self.services.keys()),))
        self.latest.im_func.pattern = re.compile(r'^(?:latest|last)\s+(%s)\s+(?:update\s+)?(?:(?:by|from|for)\s+)?(\S+)$' % ('|'.join(self.services.keys()),))

    def remote_update(self, service, id):
        f = urlopen('%sstatuses/show/%s.json' % (self.services[service], id))
        status = loads(f.read())
        f.close()

        return {'screen_name': status['user']['screen_name'], 'text': status['text']}

    def remote_latest(self, service, user):
        service_url = self.services[service]
        f = urlopen('%sstatuses/user_timeline/%s.json?count=1' % (service_url, user))
        statuses = loads(f.read())
        f.close()
        latest = statuses[0]

        if "twitter" in service_url:
            url = "%s%s/status/%i" % (service_url, latest["user"]["screen_name"], latest["id"])
        elif service_url.endswith("/api/"):
            url = "%s/notice/%i" % (service_url[:-5], latest["id"])

        return {
            'text': latest['text'],
            'ago': ago(datetime.utcnow() - datetime.strptime(latest["created_at"], '%a %b %d %H:%M:%S +0000 %Y'), 1),
            'url': url,
        }

    @handler
    def update(self, event, service, id):
        event.addresponse(u'%(screen_name)s: "%(text)s"', self.remote_update(service.lower(), int(id)))

    @handler
    def latest(self, event, service, user):
        event.addresponse(u'"%(text)s" %(ago)s ago, %(url)s', self.remote_latest(service.lower(), user))

    @match(r'^https?://(?:www\.)?twitter\.com/[^/ ]+/statuse?s?/(\d+)$')
    def twitter(self, event, id):
        event.addresponse(u'%(screen_name)s: "%(text)s"', self.remote_update('twitter', int(id)))

    @match(r'^https?://(?:www\.)?identi.ca/notice/(\d+)$')
    def identica(self, event, id):
        event.addresponse(u'%(screen_name)s: "%(text)s"', self.remote_update('identi.ca', int(id)))

help['currency'] = u'Converts amounts between currencies.'
class Currency(Processor):
    u"""exchange <amount> <currency> for <currency>
    currencies for <country>"""

    feature = "currency"

    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://www.xe.com/'}
    currencies = []

    def _load_currencies(self):
        request = Request('http://www.xe.com/iso4217.php', '', self.headers)
        f = urlopen(request)
        soup = BeautifulSoup(f.read())
        f.close()

        self.currencies = []
        for tr in soup.find('table', attrs={'class': 'tbl_main'}).table.findAll('tr'):
            code, place = tr.findAll('td')
            place = ''.join(place.findAll(text=True))
            place, name = place.find(',') != -1 and place.split(',', 1) or place.split(' ', 1)
            self.currencies.append((code.string, place.strip(), name.strip()))

    @match(r'^(?:exchange|convert)\s+([0-9.]+)\s+(\S+)\s+(?:for|to|into)\s+(\S+)$')
    def exchange(self, event, amount, frm, to):
        data = {'Amount': amount, 'From': frm, 'To': to}
        request = Request('http://www.xe.com/ucc/convert.cgi', urlencode(data), self.headers)
        f = urlopen(request)
        soup = BeautifulSoup(f.read())
        f.close()

        event.addresponse(u'%s', soup.findAll('span', attrs={'class': 'XEsmall'})[1].contents[0])

    @match(r'^(?:currency|currencies)\s+for\s+(?:the\s+)?(.+)$')
    def currency(self, event, place):
        if not self.currencies:
            self._load_currencies()

        search = re.compile(place, re.I)
        results = []
        for code, place, name in self.currencies:
            if search.search(place):
                results.append(u'%s uses %s (%s)' % (place, name, code))

        if results:
            event.addresponse(u'%s', u', '.join(results))
        else:
            event.addresponse(u'No currencies found')

help['weather'] = u'Retrieves current weather and forecasts for cities.'
class Weather(Processor):
    u"""weather in <city>
    forecast for <city>"""

    feature = "weather"

    defaults = {    'ct': 'Cape Town, South Africa',
                    'jhb': 'Johannesburg, South Africa',
                    'joburg': 'Johannesburg, South Africa',
               }
    places = Option('places', 'Alternate names for places', defaults)
    labels = ('temp', 'humidity', 'dew', 'wind', 'pressure', 'conditions', 'visibility', 'uv', 'clouds', 'ymin', 'ymax', 'ycool', 'sunrise', 'sunset', 'moonrise', 'moonset', 'moonphase', 'metar')
    whitespace = re.compile('\s+')

    class WeatherException(Exception):
        pass

    class TooManyPlacesException(WeatherException):
        pass

    def _text(self, string):
        if not isinstance(string, basestring):
            string = ''.join(string.findAll(text=True))
        return self.whitespace.sub(' ', string).strip()

    def _get_page(self, place):
        if place.lower() in self.places:
            place = self.places[place.lower()]

        f = urlopen('http://m.wund.com/cgi-bin/findweather/getForecast?brand=mobile_metric&query=' + quote(place))
        soup = BeautifulSoup(f.read(), convertEntities=BeautifulSoup.HTML_ENTITIES)
        f.close()

        if soup.body.center and soup.body.center.b.string == 'Search not found:':
            raise Weather.WeatherException(u'City not found')

        if soup.table.tr.th and soup.table.tr.th.string == 'Place: Temperature':
            places = []
            for td in soup.table.findAll('td'):
                places.append(td.find('a', href=re.compile('.*html$')).string)
            raise Weather.TooManyPlacesException(places)

        return soup

    def remote_weather(self, place):
        soup = self._get_page(place)
        tds = soup.table.table.findAll('td')

        values = {'place': tds[0].findAll('b')[1].string, 'time': tds[0].findAll('b')[0].string}
        for index, td in enumerate(tds[2::2]):
            values[self.labels[index]] = self._text(td)

        return values

    def remote_forecast(self, place):
        soup = self._get_page(place)
        forecasts = []

        for td in soup.findAll('table')[2].findAll('td', align='left'):
            day = td.b.string
            forecast = td.contents[2]
            forecasts.append(u'%s: %s' % (day, self._text(forecast)))

        return forecasts

    @match(r'^weather\s+(?:(?:for|at|in)\s+)?(.+)$')
    def weather(self, event, place):
        try:
            values = self.remote_weather(place)
            event.addresponse(u'In %(place)s at %(time)s: %(temp)s; Humidity: %(humidity)s; Wind: %(wind)s; Conditions: %(conditions)s; Sunrise/set: %(sunrise)s/%(sunset)s; Moonrise/set: %(moonrise)s/%(moonset)s', values)
        except Weather.TooManyPlacesException, e:
            event.addresponse(u'Too many places match %(place)s: %(exception)s', {
                'place': place,
                'exception': u'; '.join(e.message),
            })
        except Weather.WeatherException, e:
            event.addresponse(u'%s', e.message)

    @match(r'^forecast\s+(?:for\s+)?(.+)$')
    def forecast(self, event, place):
        try:
            event.addresponse(u'%s', u', '.join(self.remote_forecast(place)))
        except Weather.TooManyPlacesException, e:
            event.addresponse(u'Too many places match %(place)s: %(exception)s', {
                'place': place,
                'exception': u'; '.join(e.message),
            })
        except Weather.WeatherException, e:
            event.addresponse(u'%s', e.message)

# vi: set et sta sw=4 ts=4:
