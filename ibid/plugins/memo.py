from datetime import datetime
import logging

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Boolean, UnicodeText, Table
from sqlalchemy.orm import relation
from sqlalchemy.sql import func

import ibid
from ibid.plugins import Processor, handler, match, authorise
from ibid.config import Option
from ibid.plugins.auth import permission
from ibid.plugins.identity import get_identities
from ibid.models import Base, VersionedSchema, Identity, Account
from ibid.utils import ago

help = {'memo': u'Keeps messages for people.'}

memo_cache = {}
log = logging.getLogger('plugins.memo')

class Memo(Base):
    __table__ = Table('memos', Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('from_id', Integer, ForeignKey('identities.id'), nullable=False),
    Column('to_id', Integer, ForeignKey('identities.id'), nullable=False),
    Column('memo', UnicodeText, nullable=False),
    Column('private', Boolean, nullable=False),
    Column('delivered', Boolean, nullable=False),
    Column('time', DateTime, nullable=False, default=func.current_timestamp()),
    useexisting=True)

    __table__.versioned_schema = VersionedSchema(__table__, 1)

    def __init__(self, from_id, to_id, memo, private=False):
        self.from_id = from_id
        self.to_id = to_id
        self.memo = memo
        self.private = private
        self.delivered = False

Identity.memos_sent = relation(Memo, primaryjoin=Identity.id==Memo.from_id, backref='sender')
Identity.memos_recvd = relation(Memo, primaryjoin=Identity.id==Memo.to_id, backref='recipient')

class Tell(Processor):
    u"""(tell|pm|privmsg|msg) <person> <message>"""
    feature = 'memo'

    permission = u'sendmemo'
    permissions = (u'recvmemo',)

    @match(r'^(?:please\s+)?(tell|pm|privmsg|msg)\s+(\S+)\s+(?:(?:that|to)\s+)?(.+)$')
    @authorise
    def tell(self, event, how, who, memo):
        session = ibid.databases.ibid()
        to = session.query(Identity).filter(func.lower(Identity.identity)==who.lower()).filter_by(source=event.source).first()
        if not to:
            account = session.query(Account).filter(func.lower(Account.username)==who.lower()).first()
            if account:
                for identity in account.identities:
                    if identity.source == event.source:
                        to = identity
                if not identity:
                    identity = account.identities[0]
        if not to:
            to = Identity(event.source, who)
            session.save(to)
            session.flush()
            log.info(u"Created identity %s for %s on %s", to.id, to.identity, to.source)

        if permission(u'recvmemo', to.account and to.account.id or None, to.source) != 'yes':
            event.addresponse(u'Just tell %s yourself', who)
            return

        memo = Memo(event.identity, to.id, memo, how.lower() in ('pm', 'privmsg', 'msg'))
        session.save_or_update(memo)
        session.flush()
        log.info(u"Stored memo %s for %s (%s) from %s (%s): %s", memo.id, to.id, who, event.identity, event.sender['connection'], memo.memo)
        session.close()
        memo_cache.clear()

        event.addresponse(True)

def get_memos(session, event, delivered=False):
    identities = get_identities(event, session)
    return session.query(Memo).filter_by(delivered=delivered).filter(Memo.to_id.in_(identities)).order_by(Memo.time.asc()).all()

class Deliver(Processor):
    feature = 'memo'

    addressed = False
    processed = True

    @handler
    def deliver(self, event):
        if event.identity in memo_cache:
            return

        session = ibid.databases.ibid()
        memos = get_memos(session, event)

        for memo in memos:
            if memo.private:
                message = u'By the way, %(sender)s on %(source)s told me to tell you %(message)s %(ago)s ago' % {
                    'sender': memo.sender.identity,
                    'source': memo.sender.source,
                    'message': memo.memo,
                    'ago': ago(datetime.utcnow()-memo.time),
                }
                event.addresponse({'reply': message, 'target': event.sender['id']})
            else:
                event.addresponse(u'%(recipient)s: By the way, %(sender)s on %(source)s told me to tell you %(message)s %(ago)s ago', {
                    'recipient': event.sender['nick'],
                    'sender': memo.sender.identity,
                    'source': memo.sender.source,
                    'message': memo.memo,
                    'ago': ago(datetime.utcnow()-memo.time),
                })

            memo.delivered = True
            session.save_or_update(memo)
            log.info(u"Delivered memo %s to %s (%s)", memo.id, event.identity, event.sender['connection'])

        session.flush()
        session.close()
        memo_cache[event.identity] = None

class Notify(Processor):
    feature = 'memo'

    type = 'state'
    addressed = False
    processed = True

    @handler
    def state(self, event):
        if event.state not in ('joined', 'available'):
            return

        if event.identity in memo_cache:
            return

        session = ibid.databases.ibid()
        memos = get_memos(session, event)

        if len(memos) > 0:
            event.addresponse({'reply': u'You have %s messages' % len(memos), 'target': event.sender['id']})
        else:
            memo_cache[event.identity] = None

        session.close()

class Messages(Processor):
    u"""my messages
    message <number>"""
    feature = 'memo'

    datetime_format = Option('datetime_format', 'Format string for timestamps', '%Y/%m/%d %H:%M:%S')

    @match(r'^my\s+messages$')
    def messages(self, event):
        session = ibid.databases.ibid()
        memos = get_memos(session, event, True)
        if memos:
            event.addresponse(u'%s', u', '.join(['%s: %s (%s)' % (memos.index(memo), memo.sender.identity, memo.time.strftime(self.datetime_format)) for memo in memos]))
        else:
            event.addresponse(u"Sorry, nobody loves you")
        session.close()

    @match(r'^message\s+(\d+)$')
    def message(self, event, number):
        session = ibid.databases.ibid()
        memos = get_memos(session, event, True)
        memo = memos[int(number)]
        event.addresponse(u"From %(sender)s on %(source)s at %(time)s: %(message)s", {
            'sender': memo.sender.identity,
            'source': memo.sender.source,
            'time': memo.time.strftime(self.datetime_format),
            'message': memo.memo,
        })
        session.close()


# vi: set et sta sw=4 ts=4:
