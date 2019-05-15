# Copyright (c) 2008-2010, Bradley Whittington, Michael Gorven
# Released under terms of the MIT/X/Expat Licence. See COPYING for details.

import re
from urllib2 import urlopen
import logging

from ibid.plugins import Processor, match

log = logging.getLogger('plugins.lotto')

features = {'lotto': {
    'description': u'Gets the latest lotto results from the South African '
                   u'National Lottery.',
    'categories': ('lookup', 'south africa', 'web',),
}}
class Lotto(Processor):
    usage = u'lotto'

    feature = ('lotto',)

    za_url = 'http://www.nationallottery.co.za/'
    za_re = re.compile(r'images/(?:power_)?balls/(?:ball|power)_(\d+).gif')

    @match(r'^lotto(\s+for\s+south\s+africa)?$')
    def za(self, event, za):
        try:
            f = urlopen(self.za_url)
        except Exception:
            event.addresponse(u'Something went wrong getting to the Lotto site')
            return

        s = "".join(f)
        f.close()

        balls = self.za_re.findall(s)

        if len(balls) != 20:
            event.addresponse(u'I expected to get %(expected)s balls, but found %(found)s. They were: %(balls)s', {
                'expected': 20,
                'found': len(balls),
                'balls': u', '.join(balls),
            })
            return

        event.addresponse(u'Latest lotto results for South Africa, '
            u'Lotto: %(lottoballs)s (Bonus: %(lottobonus)s), '
            u'Lotto Plus: %(plusballs)s (Bonus: %(plusbonus)s), '
            u'PowerBall: %(powerballs)s PB: %(powerball)s', {
            'lottoballs': u' '.join(balls[:6]),
            'lottobonus': balls[6],
            'plusballs':  u' '.join(balls[7:13]),
            'plusbonus':  balls[13],
            'powerballs': u' '.join(balls[14:19]),
            'powerball': balls[19],
        })

# vi: set et sta sw=4 ts=4:
