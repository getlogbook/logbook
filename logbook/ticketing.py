# -*- coding: utf-8 -*-
"""
    logbook.ticketing
    ~~~~~~~~~~~~~~~~~

    Implements long handlers that write to remote data stores and assign
    each logging message a ticket id.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import hashlib
from datetime import datetime
from logbook.base import NOTSET
from logbook.handlers import Handler

try:
    import simplejson as json
except ImportError:
    import json


def to_safe_json(data):
    """Makes a data structure safe for JSON silently discarding invalid
    objects from nested structures.  This also converts dates.
    """
    _invalid = object()
    def _convert(obj):
        if obj is None:
            return None
        elif isinstance(obj, str):
            return obj.decode('utf-8', 'replace')
        elif isinstance(obj, (bool, int, long, float, unicode)):
            return obj
        elif isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%dT%H:%M:%SZ')
        elif isinstance(obj, list):
            return [x for x in map(_convert, obj) if x is not _invalid]
        elif isinstance(obj, tuple):
            return tuple(x for x in map(_convert, obj) if x is not _invalid)
        elif isinstance(obj, dict):
            rv = {}
            for key, value in obj.iteritems():
                value = _convert(value)
                if value is not _invalid:
                    if isinstance(key, str):
                        key = key.decode('utf-8', 'replace')
                    else:
                        key = unicode(key)
                    rv[key] = value
            return rv
        return _invalid
    rv = _convert(data)
    if rv is not _invalid:
        return rv


class TicketingDatabase(object):
    """Provides access to the database the :class:`TicketingDatabaseHandler`
    is using.
    """

    def __init__(self, engine_or_uri, table_prefix='logbook_', metadata=None):
        from sqlalchemy import create_engine, MetaData
        if hasattr(engine_or_uri, 'execute'):
            self.engine = engine_or_uri
        else:
            self.engine = create_engine(engine_or_uri, convert_unicode=True)
        if metadata is None:
            metadata = MetaData()
        self.table_prefix = table_prefix
        self.metadata = metadata
        self.create_tables()

    def create_tables(self):
        """Creates the tables required for the handler on the class and
        metadata.
        """
        import sqlalchemy as db
        def table(name, *args, **kwargs):
            return db.Table(self.table_prefix + name, self.metadata,
                            *args, **kwargs)
        self.tickets = table('tickets',
            db.Column('ticket_id', db.Integer, primary_key=True),
            db.Column('record_hash', db.String(40), unique=True),
            db.Column('level', db.Integer),
            db.Column('logger_name', db.String(120)),
            db.Column('location', db.String(512)),
            db.Column('module', db.String(256)),
            db.Column('last_occurrence', db.DateTime),
            db.Column('occurrence_count', db.Integer)
        )
        self.occurrences = table('occurrences',
            db.Column('occurrence_id', db.Integer, primary_key=True),
            db.Column('ticket_id', db.Integer,
                      db.ForeignKey(self.table_prefix + 'tickets.ticket_id')),
            db.Column('time', db.DateTime),
            db.Column('data', db.Text)
        )

    def _order(self, q, table, order_by):
        if order_by[0] == '-':
            return q.order_by(table.c[order_by[1:]].desc())
        return q.order_by(table.c[order_by])

    def record_ticket(self, record, data, hash):
        """Records a log record as ticket."""
        cnx = self.engine.connect()
        trans = cnx.begin()
        try:
            q = self.tickets.select(self.tickets.c.record_hash == hash)
            row = cnx.execute(q).fetchone()
            if row is None:
                row = cnx.execute(self.tickets.insert().values(
                    record_hash=hash,
                    level=record.level,
                    logger_name=record.logger_name or u'',
                    location=u'%s:%d' % (record.filename, record.lineno),
                    module=record.module or u'<unknown>',
                    occurrence_count=0
                ))
                ticket_id = row.inserted_primary_key[0]
            else:
                ticket_id = row['ticket_id']
            cnx.execute(self.occurrences.insert()
                .values(ticket_id=ticket_id,
                        time=record.time,
                        data=json.dumps(data)))
            cnx.execute(self.tickets.update()
                .where(self.tickets.c.ticket_id == ticket_id)
                .values(occurrence_count=self.tickets.c.occurrence_count + 1,
                        last_occurrence=record.time))
            trans.commit()
        except Exception:
            trans.rollback()
            raise
        cnx.close()

    def count_tickets(self):
        """Returns the number of tickets."""
        return self.engine.execute(self.tickets.count()).fetchone()[0]

    def get_tickets(self, order_by='-last_occurrence', limit=50, offset=0):
        """Selects tickets from the database."""
        return map(dict, self.engine.execute(self._order(self.tickets.select(),
            self.tickets, order_by).limit(limit).offset(offset)).fetchall())

    def get_ticket(self, ticket_id):
        """Return a single ticket with all occurrences."""
        rv = self.engine.execute(self._order(self.tickets.select(),
            self.tickets, order_by).limit(limit).offset(offset)).fetchone()
        if rv is not None:
            rv = dict(rv)
            rv['occurrences'] = self.get_occurrences(ticket_id)
            return rv

    def get_occurrences(self, ticket, order_by='-time', limit=50, offset=0):
        """Selects occurrences from the database for a ticket."""
        result = []
        for item in self.engine.execute(self._order(self.occurrences
            .select().where(self.occurrences.c.ticket_id == ticket),
            self.occurrences, order_by).limit(limit).offset(offset)).fetchall():
            d = dict(item)
            d['data'] = json.loads(d['data'])
            result.append(d)
        return result


class TicketingDatabaseHandler(Handler):
    """A handler that writes log records into a remote database.  This
    database can be connected to from different dispatchers which makes
    this a nice setup for web applications::

        from logbook.ticketing import TicketingDatabaseHandler
        handler = TicketingDatabaseHandler('sqlite:////tmp/myapp-logs.db')
    """

    def __init__(self, engine_or_uri, table_prefix='logbook_', metadata=None,
                 autocreate_tables=True, hash_salt=None, level=NOTSET,
                 filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        self.db = TicketingDatabase(engine_or_uri, table_prefix, metadata)
        self.hash_salt = hash_salt
        if autocreate_tables:
            self.db.metadata.create_all(bind=self.db.engine)

    def hash_record(self, record):
        """Returns the unique hash of a record."""
        hash = hashlib.sha1()
        hash.update((record.logger_name or u'').encode('utf-8') + '\x00')
        hash.update(record.filename.encode('utf-8') + '\x00')
        hash.update(str(record.lineno))
        if record.module:
            hash.update('\x00' + record.module)
        if self.hash_salt is not None:
            self.hash.update('\x00' + self.hash_salt)
        return hash.hexdigest()

    def process_record(self, record, hash):
        """Subclasses can override this to tamper with the data dict that
        is sent to the database as JSON.
        """
        return to_safe_json(record.to_dict())

    def emit(self, record):
        """Emits a single record and writes it to the database."""
        hash = self.hash_record(record)
        data = self.process_record(record, hash)
        self.db.record_ticket(record, data, hash)
