# Copyright (c) 2009-2010, Michael Gorven, Stefano Rivera
# Released under terms of the MIT/X/Expat Licence. See COPYING for details.

from unicodedata import normalize
from random import choice, random
import re

from nickometer import nickometer

import ibid
from ibid.plugins import Processor, match
from ibid.config import IntOption, ListOption
from ibid.utils import human_join

features = {}

features['nickometer'] = {
    'description': u'Calculates how lame a nick is.',
    'categories': ('fun', 'calculate',),
}
class Nickometer(Processor):
    usage = u'nickometer [<nick>] [with reasons]'
    feature = ('nickometer',)

    @match(r'^(?:nick|lame)-?o-?meter(?:(?:\s+for)?\s+(.+?))?(\s+with\s+reasons)?$')
    def handle_nickometer(self, event, nick, wreasons):
        nick = nick or event.sender['nick']
        if u'\ufffd' in nick:
            score, reasons = 100., ((u'Not UTF-8 clean', u'infinite'),)
        else:
            score, reasons = nickometer(normalize('NFKD', nick).encode('ascii', 'ignore'))

        event.addresponse(u'%(nick)s is %(score)s%% lame', {
            'nick': nick,
            'score': score,
        })
        if wreasons:
            if not reasons:
                reasons = ((u'A good, traditional nick', 0),)
            event.addresponse(u'Because: %s', u', '.join(['%s (%s)' % reason for reason in reasons]))

features['choose'] = {
    'description': u'Choose one of the given options.',
    'categories': ('fun', 'decide',),
}
class Choose(Processor):
    usage = u'choose <choice> or <choice>...'
    feature = ('choose',)

    choose_re = re.compile(r'(?:\s*,\s*(?:or\s+)?)|(?:\s+or\s+)', re.I)

    @match(r'^(?:choose|choice|pick)\s+(.+)$')
    def choose(self, event, choices):
        event.addresponse(u'I choose %s', choice(self.choose_re.split(choices)))

features['coffee'] = {
    'description': u'Times coffee brewing and reserves cups for people',
    'categories': ('fun', 'monitor',),
}
class Coffee(Processor):
    usage = u'coffee (on|please)'
    feature = ('coffee',)

    pots = {}

    time = IntOption('coffee_time', u'Brewing time in seconds', 240)
    cups = IntOption('coffee_cups', u'Maximum number of cups', 4)

    def coffee_announce(self, event):
        event.addresponse(u"Coffee's ready for %s!",
                human_join(self.pots[(event.source, event.channel)]))
        del self.pots[(event.source, event.channel)]

    @match(r'^coffee\s+on$')
    def coffee_on(self, event):
        if (event.source, event.channel) in self.pots:
            if len(self.pots[(event.source, event.channel)]) >= self.cups:
                event.addresponse(u"There's already a pot on, and it's all reserved")
            elif event.sender['nick'] in self.pots[(event.source, event.channel)]:
                event.addresponse(u"You already have a pot on the go")
            else:
                event.addresponse(u"There's already a pot on. If you ask nicely, maybe you can have a cup")
            return

        self.pots[(event.source, event.channel)] = [event.sender['nick']]
        ibid.dispatcher.call_later(self.time, self.coffee_announce, event)

        event.addresponse(choice((
                u'puts the kettle on',
                u'starts grinding coffee',
                u'flips the salt-timer',
                u'washes some mugs',
            )), action=True)

    @match('^coffee\s+(?:please|pls)$')
    def coffee_accept(self, event):
        if (event.source, event.channel) not in self.pots:
            event.addresponse(u"There isn't a pot on")

        elif len(self.pots[(event.source, event.channel)]) >= self.cups:
            event.addresponse(u"Sorry, there aren't any more cups left")

        elif event.sender['nick'] in self.pots[(event.source, event.channel)]:
            event.addresponse(u"Now now, we don't want anyone getting caffeine overdoses")

        else:
            self.pots[(event.source, event.channel)].append(event.sender['nick'])
            event.addresponse(True)

features['insult'] = {
    'description': u'Slings verbal abuse at someone',
    'categories': ('fun',),
}
class Insult(Processor):
    usage = u"""(flame | insult) <person>
    (swear | cuss | explete) [at <person>]"""
    feature = ('insult',)

    adjectives = ListOption('adjectives', 'List of adjectives', (
        u'acidic', u'antique', u'artless', u'base-court', u'bat-fowling',
        u'bawdy', u'beef-witted', u'beetle-headed', u'beslubbering',
        u'boil-brained', u'bootless', u'churlish', u'clapper-clawed',
        u'clay-brained', u'clouted', u'cockered', u'common-kissing',
        u'contemptible', u'coughed-up', u'craven', u'crook-pated',
        u'culturally-unsound', u'currish', u'dankish', u'decayed',
        u'despicable', u'dismal-dreaming', u'dissembling', u'dizzy-eyed',
        u'doghearted', u'dread-bolted', u'droning', u'earth-vexing',
        u'egg-sucking', u'elf-skinned', u'errant', u'evil', u'fat-kidneyed',
        u'fawning', u'fen-sucked', u'fermented', u'festering', u'flap-mouthed',
        u'fly-bitten', u'fobbing', u'folly-fallen', u'fool-born', u'foul',
        u'frothy', u'froward', u'full-gorged', u'fulminating', u'gleeking',
        u'goatish', u'gorbellied', u'guts-griping', u'hacked-up', u'halfbaked',
        u'half-faced', u'hasty-witted', u'headless', u'hedge-born',
        u'hell-hated', u'horn-beat', u'hugger-muggered', u'humid',
        u'idle-headed', u'ill-borne', u'ill-breeding', u'ill-nurtured',
        u'imp-bladdereddle-headed', u'impertinent', u'impure', u'industrial',
        u'inept', u'infected', u'infectious', u'inferior', u'it-fowling',
        u'jarring', u'knotty-pated', u'left-over', u'lewd-minded',
        u'loggerheaded', u'low-quality', u'lumpish', u'malodorous',
        u'malt-wormy', u'mammering', u'mangled', u'measled', u'mewling',
        u'milk-livered', u'motley-mind', u'motley-minded', u'off-color',
        u'onion-eyed', u'paunchy', u'penguin-molesting', u'petrified',
        u'pickled', u'pignutted', u'plume-plucked', u'pointy-nosed', u'porous',
        u'pottle-deep', u'pox-marked', u'pribbling', u'puking', u'puny',
        u'railing', u'rank', u'reeky', u'reeling-ripe', u'roguish',
        u'rough-hewn', u'rude-growing', u'rude-snouted', u'rump-fed',
        u'ruttish', u'salty', u'saucy', u'saucyspleened', u'sausage-snorfling',
        u'shard-borne', u'sheep-biting', u'spam-sucking', u'spleeny',
        u'spongy', u'spur-galled', u'squishy', u'surly', u'swag-bellied',
        u'tardy-gaited', u'tastless', u'tempestuous', u'tepid', u'thick',
        u'tickle-brained', u'toad-spotted', u'tofu-nibbling', u'tottering',
        u'uninspiring', u'unintelligent', u'unmuzzled', u'unoriginal',
        u'urchin-snouted', u'vain', u'vapid', u'vassal-willed', u'venomed',
        u'villainous', u'warped', u'wayward', u'weasel-smelling',
        u'weather-bitten', u'weedy', u'wretched', u'yeasty',
    ))

    collections = ListOption('collections', 'List of collective nouns', (
        u'accumulation', u'ass-full', u'assload', u'bag', u'bucket',
        u'coagulation', u'enema-bucketful', u'gob', u'half-mouthful', u'heap',
        u'mass', u'mound', u'ooze', u'petrification', u'pile', u'plate',
        u'puddle', u'quart', u'stack', u'thimbleful', u'tongueful',
    ))

    nouns = ListOption('nouns', u'List of singular nouns', (
        u'apple-john', u'baggage', u'barnacle', u'bladder', u'boar-pig',
        u'bugbear', u'bum-bailey', u'canker-blossom', u'clack-dish',
        u'clotpole', u'coxcomb', u'codpiece', u'death-token', u'dewberry',
        u'flap-dragon', u'flax-wench', u'flirt-gill', u'foot-licker',
        u'fustilarian', u'giglet', u'gudgeon', u'haggard', u'harpy',
        u'hedge-pig', u'horn-beast', u'hugger-mugger', u'jolthead',
        u'lewdster', u'lout', u'maggot-pie', u'malt-worm', u'mammet',
        u'measle', u'minnow', u'miscreant', u'moldwarp', u'mumble-news',
        u'nut-hook', u'pigeon-egg', u'pignut', u'puttock', u'pumpion',
        u'ratsbane', u'scut', u'skainsmate', u'strumpet', u'varlet', u'vassal',
        u'whey-face', u'wagtail',
    ))

    plnouns = ListOption('plnouns', u'List of plural nouns', (
        u'anal warts', u'armadillo snouts', u'bat toenails', u'bug spit',
        u'buzzard gizzards', u'cat bladders', u'cat hair', u'cat-hair-balls',
        u'chicken piss', u'cold sores', u'craptacular carpet droppings',
        u'dog balls', u'dog vomit', u'dung', u'eel ooze', u'entrails',
        u"fat-woman's stomach-bile", u'fish heads', u'guano', u'gunk',
        u'jizzum', u'pods', u'pond scum', u'poop', u'poopy', u'pus',
        u'rat-farts', u'rat retch', u'red dye number-9', u'seagull puke',
        u'slurpee-backwash', u'snake assholes', u'snake bait', u'snake snot',
        u'squirrel guts', u'Stimpy-drool', u'Sun IPC manuals', u'toxic waste',
        u'urine samples', u'waffle-house grits', u'yoo-hoo',
    ))

    @match(r'^(?:insult|flame)\s+(.+)$')
    def insult(self, event, insultee):
        articleadj = choice(self.adjectives)
        articleadj = (articleadj[0] in u'aehiou' and u'an ' or u'a ') + articleadj

        event.addresponse(choice((
            u'%(insultee)s, thou %(adj1)s, %(adj2)s %(noun)s',
            u'%(insultee)s is nothing but %(articleadj)s %(collection)s of %(adj1)s %(plnoun)s',
        )), {
            'insultee': insultee,
            'adj1': choice(self.adjectives),
            'adj2': choice(self.adjectives),
            'articleadj': articleadj,
            'collection': choice(self.collections),
            'noun': choice(self.nouns),
            'plnoun': choice(self.plnouns),
        }, address=False)

    loneadjectives = ListOption('loneadjectives',
        'List of stand-alone adjectives for swearing', (
            'bloody', 'damn', 'fucking', 'shitting', 'sodding', 'crapping',
            'wanking', 'buggering',
    ))

    swearadjectives = ListOption('swearadjectives',
        'List of adjectives to be combined with swearnouns', (
            'reaming', 'lapping', 'eating', 'sucking', 'vokken', 'kak',
            'donder', 'bliksem', 'fucking', 'shitting', 'sodding', 'crapping',
            'wanking', 'buggering',
    ))

    swearnouns = ListOption('swearnouns',
        'List of nounes to be comined with swearadjectives', (
            'shit', 'cunt', 'hell', 'mother', 'god', 'maggot', 'father', 'crap',
            'ball', 'whore', 'goat', 'dick', 'cock', 'pile', 'bugger', 'poes',
            'hoer', 'kakrooker', 'ma', 'pa', 'naiier', 'kak', 'bliksem',
            'vokker', 'kakrooker',
    ))

    swearlength = IntOption('swearlength', 'Number of expletives to swear with',
                            15)

    @match(r'^(?:swear|cuss|explete)(?:\s+at\s+(?:the\s+)?(.*))?$')
    def swear(self, event, insultee):
        swearage = []
        for i in range(self.swearlength):
            if random() > 0.7:
                swearage.append(choice(self.loneadjectives))
            else:
                swearage.append(choice(self.swearnouns)
                                + choice(self.swearadjectives))
        if insultee is not None:
            swearage.append(insultee)
        else:
            swearage.append(choice(self.swearnouns))

        event.addresponse(u' '.join(swearage) + u'!', address=False)

# vi: set et sta sw=4 ts=4:
