import re

from ibid.plugins import Processor, match

help = {}

help["morse"] = u"Translates messages into and out of morse code."

class Morse(Processor):
    u"""morse (text|morsecode)"""
    feature = 'morse'
    
    _table = {
        'A': ".-",
        'B': "-...",
        'C': "-.-.",
        'D': "-..",
        'E': ".",
        'F': "..-.",
        'G': "--.",
        'H': "....",
        'I': "..",
        'J': ".---",
        'K': "-.-",
        'L': ".-..",
        'M': "--",
        'N': "-.",
        'O': "---",
        'P': ".--.",
        'Q': "--.-",
        'R': ".-.",
        'S': "...",
        'T': "-",
        'U': "..-",
        'V': "...-",
        'W': ".--",
        'X': "-..-",
        'Y': "-.--",
        'Z': "--..",
        '0': "-----",
        '1': ".----",
        '2': "..---",
        '3': "...--",
        '4': "....-",
        '5': ".....",
        '6': "-....",
        '7': "--...",
        '8': "---..",
        '9': "----.",
        ' ': " ",
        '.': ".-.-.-",
        ',': "--..--",
        '?': "..--..",
        ':': "---...",
        ';': "-.-.-.",
        '-': "-....-",
        '_': "..--.-",
        '"': ".-..-.",
        "'": ".----.",
        '/': "-..-.",
        '(': "-.--.",
        ')': "-.--.-",
        '=': "-...-",
    }
    _rtable = dict((v, k) for k, v in _table.items())
    _raw_match_re = re.compile(r'^.*?morse\s+(.+)$')

    def _text2morse(self, text):
        return u" ".join(self._table.get(c.upper(), c) for c in text)

    def _morse2text(self, morse):
        toks = morse.split(u' ')
        return u"".join(self._rtable.get(t, u' ') for t in toks)

    @match(r'^morse\s*(.*)$')
    def morse(self, event, message):
        if "message_raw" in event:
            message = self._raw_match_re.match(event.message_raw).group(1)

        if message.replace(u'-', u'').replace(u'.', u'').strip() == u'':
            event.addresponse(u'Decodes as %s', self._morse2text(message))
        else:
            event.addresponse(u'Encodes as %s', self._text2morse(message))

# vi: set et sta sw=4 ts=4:
