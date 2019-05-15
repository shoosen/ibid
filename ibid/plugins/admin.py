# Copyright (c) 2008-2010, Michael Gorven
# Released under terms of the MIT/X/Expat Licence. See COPYING for details.

from os.path import join
from twisted.internet import reactor
import logging

import ibid
from ibid.utils import human_join
from ibid.config import FileConfig
from ibid.plugins import Processor, match, authorise, auth_responses
from ibid.utils import ibid_version

log = logging.getLogger('plugins.admin')

features = {}

features['plugins'] = {
    'description': u'Lists, loads and unloads plugins.',
    'categories': ('admin',),
}
class ListPLugins(Processor):
    usage = u'list plugins'
    feature = ('plugins',)

    @match(r'^lsmod|list\s+plugins$')
    def handler(self, event):
        plugins = []
        for processor in ibid.processors:
            if processor.name not in plugins:
                plugins.append(processor.name)

        event.addresponse(u'Plugins: %s', human_join(sorted(plugins)) or u'none')

features['core'] = {
    'description': u'Reloads core modules.',
    'categories': ('admin',),
}
class ReloadCoreModules(Processor):
    usage = u'reload (reloader|dispatcher|databases|auth)'
    feature = ('core',)

    priority = -5
    permission = u'core'

    @match(r'^reload\s+(reloader|dispatcher|databases|auth)$')
    @authorise()
    def reload(self, event, module):
        module = module.lower()
        if module == 'reloader':
            result = ibid.reload_reloader()
        else:
            result = getattr(ibid.reloader, 'reload_%s' % module)()

        event.addresponse(result and u'%s reloaded' or u"Couldn't reload %s", module)

class LoadModules(Processor):
    usage = u'(load|unload|reload) <plugin|processor>'
    feature = ('plugins',)

    permission = u'plugins'

    @match(r'^(?:re)?load\s+(\S+)(?:\s+plugin)?$')
    @authorise()
    def load(self, event, plugin):
        result = ibid.reloader.unload_processor(plugin)
        result = ibid.reloader.load_processor(plugin)
        event.addresponse(result and u'%s reloaded' or u"Couldn't reload %s", plugin)

    @match(r'^unload\s+(\S+)$')
    @authorise()
    def unload(self, event, plugin):
        result = ibid.reloader.unload_processor(plugin)
        event.addresponse(result and u'%s unloaded' or u"Couldn't unload %s", plugin)

features['die'] = {
    'description': u'Terminates the bot',
    'categories': ('admin',),
}
class Die(Processor):
    usage = u'die'
    feature = ('die',)

    permission = u'admin'

    @match(r'^die$')
    @authorise()
    def die(self, event):
        reactor.stop()

features['sources'] = {
    'description': u'Controls and lists the configured sources.',
    'categories': ('admin',),
}
class Admin(Processor):
    usage = u"""(connect|disconnect) (to|from) <source>
    load <source> source"""
    feature = ('sources',)

    permission = u'sources'

    @match(r'^connect\s+(?:to\s+)?(\S+)$')
    @authorise()
    def connect(self, event, source):
        if source not in ibid.sources:
            event.addresponse(u"I don't have a source called %s", source)
        elif ibid.sources[source].connect():
            event.addresponse(u'Connecting to %s', source)
        else:
            event.addresponse(u"I couldn't connect to %s", source)

    @match(r'^disconnect\s+(?:from\s+)?(\S+)$')
    @authorise()
    def disconnect(self, event, source):
        if source not in ibid.sources:
            event.addresponse(u"I am not connected to %s", source)
        elif ibid.sources[source].disconnect():
            event.addresponse(u'Disconnecting from %s', source)
        else:
            event.addresponse(u"I couldn't disconnect from %s", source)

    @match(r'^(?:re)?load\s+(\S+)\s+source$')
    @authorise()
    def load(self, event, source):
        if ibid.reloader.load_source(source, ibid.service):
            event.addresponse(u"%s source loaded", source)
        else:
            event.addresponse(u"Couldn't load %s source", source)

class Info(Processor):
    usage = u'(sources|list configured sources)'
    feature = ('sources',)

    @match(r'^sources$')
    def list(self, event):
        sources = []
        for name, source in ibid.sources.items():
            url = source.url()
            sources.append(url and u'%s (%s)' % (name, url) or name)
        event.addresponse(u'Sources: %s', human_join(sorted(sources)) or u'none')

    @match(r'^list\s+configured\s+sources$')
    def listall(self, event):
        event.addresponse(u'Configured sources: %s', human_join(sorted(ibid.config.sources.keys())) or u'none')

features['version'] = {
    'description': u'Show the Ibid version currently running',
    'categories': ('admin',),
}
class Version(Processor):
    usage = u'version'
    feature = ('version',)

    @match(r'^version$')
    def show_version(self, event):
        if ibid_version():
            event.addresponse(u'I am version %s', ibid_version())
        else:
            event.addresponse(u"I don't know what version I am :-(")

features['config'] = {
    'description': u'Gets and sets configuration settings, and rereads the '
                   u'configuration file.',
    'categories': ('admin',),
}
class Config(Processor):
    usage = u"""reread config
    set config <name> to <value>
    get config <name>"""
    feature = ('config',)

    priority = -10
    permission = u'config'

    @match(r'^reread\s+config$')
    @authorise()
    def reload(self, event):
        ibid.config.reload()
        ibid.config.merge(FileConfig(join(ibid.options['base'], 'local.ini')))
        ibid.reloader.reload_config()
        ibid.auth.drop_caches()
        event.addresponse(True)
        log.info(u'Reread configuration file')

    @match(r'^(?:set\s+config|config\s+set)\s+(\S+?)(?:\s+to\s+|\s*=\s*)(\S.*?)$')
    @authorise()
    def set(self, event, key, value):
        config = ibid.config
        for part in key.split('.')[:-1]:
            if isinstance(config, dict):
                if part not in config:
                    config[part] = {}
            else:
                event.addresponse(u'No such option')
                return

            config = config[part]

        part = key.split('.')[-1]
        if not isinstance(config, dict):
            event.addresponse(u'No such option')
            return
        if ',' in value:
            config[part] = [part.strip() for part in value.split(',')]
        else:
            config[part] = value

        ibid.config.write()
        ibid.reloader.reload_config()
        log.info(u"Set %s to %s", key, value)

        event.addresponse(True)

    @match(r'^(?:get\s+config|config\s+get)\s+(\S+?)$')
    def get(self, event, key):
        if 'password' in key.lower() and not auth_responses(event, u'config'):
            return

        config = ibid.config
        for part in key.split('.'):
            if not isinstance(config, dict) or part not in config:
                event.addresponse(u'No such option')
                return
            config = config[part]
        if isinstance(config, list):
            event.addresponse(u', '.join(config))
        elif isinstance(config, dict):
            event.addresponse(u'Keys: ' + human_join(config.keys()))
        else:
            event.addresponse(unicode(config))

# vi: set et sta sw=4 ts=4:
