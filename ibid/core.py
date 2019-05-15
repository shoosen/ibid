# Copyright (c) 2008-2011, Michael Gorven, Jonathan Hitchcock, Stefano Rivera,
# Max Rabkin
# Released under terms of the MIT/X/Expat Licence. See COPYING for details.

from cgi import parse_qs
import inspect
import re
import logging
import socket
from os.path import join, expanduser
import sys

from twisted.internet import reactor, threads
from twisted.python.modules import getModule
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError

import ibid
from ibid.event import Event
from ibid.db import SchemaVersionException, schema_version_check
from ibid.utils import JSONException

import auth

def process(event, log):
    for processor in ibid.processors:
        try:
            processor.process(event)
        except Exception, e:
            log.exception(
                    u'Exception occured in %s processor of %s plugin.\n'
                    u'Event: %s',
                    processor.__class__.__name__,
                    processor.name,
                    event)
            event.complain = isinstance(e, (IOError, socket.error, JSONException)) and u'network' or u'exception'
            event.exc_info = sys.exc_info()
            event.processed = True
            if 'session' in event:
                event.session.rollback()
                event.session.close()
                del event['session']

        if 'session' in event and (event.session.dirty or event.session.deleted):
            try:
                event.session.commit()
            except IntegrityError:
                log.exception(u"Exception occured committing session from the %s processor of %s plugin",
                        processor.__class__.__name__, processor.name)
                event.complain = u'exception'
                event.exc_info = sys.exc_info()
                event.session.rollback()
                event.session.close()
                del event['session']

    if 'session' in event:
        event.session.close()
        del event['session']

class Dispatcher(object):

    def __init__(self):
        self.log = logging.getLogger('core.dispatcher')

    def _process(self, event):
        process(event, self.log)

        log_level = logging.DEBUG
        if event.type == u'clock' and not event.processed:
            log_level -= 5
        self.log.log(log_level, event)

        filtered = []
        for response in event['responses']:
            if response['source'] == event.source:
                filtered.append(response)
            else:
                self.send(response)

        event.responses = filtered
        self.log.log(log_level, u"Returning event to %s source", event.source)

        return event

    def send(self, response):
        source = response['source']
        if source in ibid.sources:
            reactor.callFromThread(ibid.sources[source].send, response)
            self.log.debug(u"Sent response to non-origin source %s: %s", response['source'], response['reply'])
        else:
            self.log.warning(u'Received response for invalid source %s: %s', response['source'], response['reply'])

    def dispatch(self, event):
        log_level = logging.DEBUG
        if event.type == u'clock':
            log_level -= 5
        self.log.log(log_level, u"Received event from %s source", event.source)

        return threads.deferToThread(self._process, event)

    def call_later(self, delay, callable, oldevent, *args, **kw):
        "Run callable after delay seconds. Pass args and kw to it"

        event = Event(oldevent.source, u'delayed')
        event.sender = oldevent.sender
        event.channel = oldevent.channel
        event.public = oldevent.public
        return reactor.callLater(delay, threads.deferToThread, self.delayed_call, callable, event, *args, **kw)

    def delayed_call(self, callable, event, *args, **kw):
        # Twisted doesn't catch exceptions here, so we must do it ourselves
        try:
            callable(event, *args, **kw)
            self._process(event)
            reactor.callFromThread(self.delayed_response, event)
        except:
            self.log.exception(u'Call Later')

    def delayed_response(self, event):
        for response in event.responses:
            ibid.sources[event.source].send(response)

class Reloader(object):

    def __init__(self):
        self.log = logging.getLogger('core.reloader')

    def run(self):
        self.reload_dispatcher()
        self.load_sources()
        self.load_processors()
        reactor.run()

    def reload_dispatcher(self):
        try:
            reload(ibid.core)
            dispatcher = ibid.core.Dispatcher()
            ibid.dispatcher = dispatcher
            self.log.info(u"Reloaded reloader")
            return True
        except Exception, e:
            self.log.error(u"Failed to reload reloader: %s", unicode(e))
            return False

    def load_source(self, name, service=None):
        type = 'type' in ibid.config.sources[name] and ibid.config.sources[name]['type'] or name

        module = 'ibid.source.%s' % type
        factory = 'ibid.source.%s.SourceFactory' % type
        try:
            __import__(module)
            moduleclass = eval(factory)
        except:
            self.log.exception(u"Couldn't import %s and instantiate %s", module, factory)
            return

        ibid.sources[name] = moduleclass(name)
        ibid.sources[name].setServiceParent(service)
        self.log.info(u"Loaded %s source %s", type, name)
        return True

    def load_sources(self, service=None):
        for source in ibid.config.sources.keys():
            if not ibid.config.sources[source].get('disabled', False):
                self.load_source(source, service)

    def unload_source(self, name):
        if name not in ibid.sources:
            return False

        ibid.sources[name].protocol.loseConnection()
        del ibid.sources[name]
        self.log.info(u"Unloaded %s source", name)

    def reload_source(self, name):
        if name not in ibid.config['sources']:
            return False

        self.unload_source(name)

        source = ibid.config['sources'][name]
        m=eval('ibid.source.%s' % source['type'])
        reload(m)

        self.load_source(source)

    def load_processors(self, load=None, noload=None, autoload=None):
        """If method parameters are not provided, they'll be looked up from
        config:
        [plugins]
            load = List of plugins / plugin.Processors to load
            noload = List of plugins / plugin.Processors to skip automatically loading
            autoload = (Boolean) Load all plugins by default?
        """
        # Sets up twisted.python so that we can iterate modules
        __import__('ibid.plugins')

        if load is None:
            load = ibid.config.plugins.get('load', [])
        if noload is None:
            noload = ibid.config.plugins.get('noload', [])

        all_plugins = set(plugin.split('.')[0] for plugin in load)
        if autoload is None:
            autoload = ibid.config.plugins.get('autoload', True)

        if autoload:
            all_plugins |= set(plugin.name.replace('ibid.plugins.', '')
                    for plugin in getModule('ibid.plugins').iterModules())

        for plugin in all_plugins:
            load_processors = [p.split('.')[1] for p in load if p.startswith(plugin + '.')]
            noload_processors = [p.split('.')[1] for p in noload if p.startswith(plugin + '.')]
            if plugin not in noload or load_processors:
                self.load_processor(plugin, noload=noload_processors, load=load_processors, load_all=(plugin in load), noload_all=(plugin in noload))

    def load_processor(self, name, noload=[], load=[], load_all=False, noload_all=False):
        """Load processor <name>.
        Skip the Processors in noload.
        Load the Processors in load.
        If load_all, the autoload attribute on each Processor isn't checked.
        If noload_all, only Processors in load are loaded.
        """
        module = 'ibid.plugins.' + name
        try:
            __import__(module)
            m = eval(module)
            reload(m)
        except Exception, e:
            if isinstance(e, ImportError):
                error = u"Couldn't load %s plugin because it requires module %s" % (name, e.args[0].replace('No module named ', ''))
                self.log.warning(error)
            else:
                self.log.exception(u"Couldn't load %s plugin", name)
            return False

        for classname, klass in inspect.getmembers(m, inspect.isclass):
            if (issubclass(klass, ibid.plugins.Processor)
                    and klass != ibid.plugins.Processor):
                if (klass.__name__ not in noload and (klass.__name__ in load
                        or ((load_all or klass.autoload) and not noload_all))):
                    self.log.debug("Loading Processor: %s.%s", name,
                                   klass.__name__)
                    try:
                        ibid.processors.append(klass(name))
                    except Exception, e:
                        self.log.exception(u"Couldn't instantiate %s "
                                           u"processor of %s plugin",
                                           classname, name)
                        continue
                else:
                    self.log.debug("Skipping Processor: %s.%s", name,
                                   klass.__name__)

        try:
            schema_version_check(ibid.databases['ibid'])
        except SchemaVersionException, e:
            self.log.error(u'Tables out of date: %s. Run "ibid-db --upgrade"',
                           e.message)

        ibid.processors.sort(key=lambda x: x.priority)

        self.log.debug(u"Loaded %s plugin", name)
        return True

    def unload_processor(self, name):
        processors = []

        for processor in ibid.processors:
            if processor.name == name:
                processors.append(processor)

        if processors:
            for processor in processors:
                processor.shutdown()
                ibid.processors.remove(processor)

            self.log.info(u"Unloaded %s plugin", name)
            return True

    def reload_databases(self):
        reload(ibid.core)
        ibid.databases = DatabaseManager()
        return True

    def reload_auth(self):
        try:
            reload(auth)
            ibid.auth = auth.Auth()
            self.log.info(u'Reloaded auth')
            return True
        except Exception, e:
            self.log.error(u"Couldn't reload auth: %s", unicode(e))

        return False

    def reload_config(self):
        for processor in ibid.processors:
            processor.setup()
        for source in ibid.sources:
            ibid.sources[source].setup()
        self.log.info(u"Notified all processors of config reload")

def regexp(pattern, item):
    return re.search(pattern, item, re.I) and True or False

def sqlite_creator(database, synchronous=True):
    try:
        from pysqlite2 import dbapi2 as sqlite
    except ImportError:
        from sqlite3 import dbapi2 as sqlite

    def connect():
        connection = sqlite.connect(database)
        connection.create_function('regexp', 2, regexp)
        if not synchronous:
            connection.execute('PRAGMA synchronous = OFF')
        connection.execute('PRAGMA foreign_keys=ON')
        return connection
    return connect

class DatabaseManager(dict):

    def __init__(self, check_schema_versions=True, sqlite_synchronous=True):
        self.log = logging.getLogger('core.databases')
        self.sqlite_synchronous = sqlite_synchronous
        for database in ibid.config.databases.keys():
            self.load(database)

        if check_schema_versions:
            try:
                schema_version_check(self['ibid'])
            except SchemaVersionException, e:
                self.log.error(u'Tables out of date: %s. Run "ibid-db --upgrade"', e.message)
                raise

    def load(self, name):
        uri = ibid.config.databases[name]
        echo = ibid.config.debugging.get(u'sqlalchemy_echo', False)

        if uri.startswith('sqlite:///'):
            engine = create_engine('sqlite:///',
                creator=sqlite_creator(join(ibid.options['base'],
                        expanduser(uri.replace('sqlite:///', '', 1))),
                    self.sqlite_synchronous),
                encoding='utf-8', convert_unicode=True,
                echo=echo
            )

        elif uri.startswith(u'mysql://'):
            if u'?' not in uri:
                uri += u'?'
            params = parse_qs(uri.split(u'?', 1)[1])
            if u'charset' not in params:
                uri += u'&charset=utf8'
            if u'sql_mode' not in params:
                uri += u'&sql_mode=ANSI_QUOTES'
            # As recommended by SQLAlchemy due to a memory leak:
            # http://www.sqlalchemy.org/trac/wiki/DatabaseNotes
            if u'use_unicode' not in params:
                uri += u'&use_unicode=0'

            engine = create_engine(uri, encoding='utf-8',
                convert_unicode=True, echo=echo,
                # MySQL closes 8hr old connections:
                pool_recycle=3600)

            class MySQLModeListener(object):
                def connect(self, dbapi_con, con_record):
                    mysql_engine = ibid.config.get('mysql_engine', 'InnoDB')
                    c = dbapi_con.cursor()
                    c.execute("SET SESSION default_storage_engine=%s;"
                              % mysql_engine)
                    c.execute("SET SESSION time_zone='+0:00';")
                    c.close()
            engine.pool.add_listener(MySQLModeListener())

        elif uri.startswith('postgres://'):
            engine = create_engine(uri, encoding='utf-8',
                convert_unicode=True, assert_unicode=True, echo=echo,
                # Ensure decoded unicode values are returned:
                use_native_unicode=False)

            class PGSQLModeListener(object):
                def connect(self, dbapi_con, con_record):
                    c = dbapi_con.cursor()
                    c.execute("SET TIME ZONE UTC")
                    c.close()

            engine.pool.add_listener(PGSQLModeListener())

        self[name] = scoped_session(sessionmaker(bind=engine))

        self.log.info(u"Loaded %s database", name)

    def __getattr__(self, name):
        return self[name]

# vi: set et sta sw=4 ts=4:
