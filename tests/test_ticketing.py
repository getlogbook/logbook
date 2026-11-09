import json
import os
from datetime import datetime, timezone
from threading import get_ident

import pytest

import logbook

from .utils import require_module

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith(".pyc"):
    __file_without_pyc__ = __file_without_pyc__[:-1]


@require_module("sqlalchemy")
def test_basic_ticketing(logger):
    from time import sleep

    from logbook.ticketing import TicketingHandler

    with TicketingHandler("sqlite:///") as handler:
        for x in range(5):
            logger.warning("A warning")
            sleep(0.2)
            logger.info("An error")
            sleep(0.2)
            if x < 2:
                try:
                    1 / 0  # noqa: B018
                except Exception:
                    logger.exception()

    assert handler.db.count_tickets() == 3
    tickets = handler.db.get_tickets()
    assert len(tickets) == 3
    assert tickets[0].level == logbook.INFO
    assert tickets[1].level == logbook.WARNING
    assert tickets[2].level == logbook.ERROR
    assert tickets[0].occurrence_count == 5
    assert tickets[1].occurrence_count == 5
    assert tickets[2].occurrence_count == 2
    assert tickets[0].last_occurrence.level == logbook.INFO

    tickets[0].solve()
    assert tickets[0].solved
    tickets[0].delete()

    ticket = handler.db.get_ticket(tickets[1].ticket_id)
    assert ticket == tickets[1]

    occurrences = handler.db.get_occurrences(tickets[2].ticket_id, order_by="time")
    assert len(occurrences) == 2
    record = occurrences[0]
    assert __file_without_pyc__ in record.filename
    assert record.func_name == "test_basic_ticketing"
    assert record.level == logbook.ERROR
    assert record.thread == get_ident()
    assert record.process == os.getpid()
    assert record.channel == "testlogger"
    assert "1 / 0" in record.formatted_exception


@require_module("sqlalchemy")
def test_engine_ticketing():
    from sqlalchemy import create_engine

    from logbook.ticketing import TicketingHandler

    engine = create_engine("sqlite:///")
    try:
        handler = TicketingHandler(engine)
        assert handler.db.engine is engine
        record = logbook.LogRecord("test", logbook.WARNING, "engine")
        record.heavy_init()
        handler.emit(record)
        [ticket] = handler.db.get_tickets()
        assert ticket.last_occurrence.message == "engine"
    finally:
        engine.dispose()


@pytest.fixture
def couchdb_backend():
    from logbook.more import CouchDBBackend

    class JSONDatabase:
        def __init__(self):
            self.documents = []

        def save(self, document):
            # Like the real client: documents must be JSON, and save() adds
            # _id and _rev to the dict it is given.
            self.documents.append(json.loads(json.dumps(document)))
            document.setdefault("_id", "ticket-id")
            document["_rev"] = str(len(self.documents))
            return document["_id"], document["_rev"]

    database = JSONDatabase()

    class Backend(CouchDBBackend):
        def setup_backend(self):
            self.database = database

    return Backend, database


def test_couchdb_stores_json_safe_processed_record(couchdb_backend):
    from logbook.ticketing import TicketingHandler

    backend, database = couchdb_backend
    handler = TicketingHandler("http://example.invalid/", backend=backend)
    record = logbook.LogRecord(
        "test",
        logbook.WARNING,
        "message",
        extra={
            "nested": {"when": datetime(2020, 1, 2, 3, 4, 5, 123456)},
            "values": (None, object(), 42),
        },
    )
    record.heavy_init()
    handler.emit(record)

    stored = database.documents[0]
    assert stored["extra"]["nested"]["when"] == "2020-01-02T03:04:05.123456Z"
    assert stored["extra"]["values"] == [None, None, 42]


def test_couchdb_process_record_hook(couchdb_backend):
    from logbook.ticketing import TicketingHandler

    backend, database = couchdb_backend

    class ProcessedHandler(TicketingHandler):
        def process_record(self, record, hash):
            data = super().process_record(record, hash)
            data["processed_marker"] = {"source": "application"}
            self.processed = data
            return data

    handler = ProcessedHandler("http://example.invalid/", backend=backend)
    record = logbook.LogRecord("test", logbook.WARNING, "message")
    record.heavy_init()
    handler.emit(record)

    assert database.documents[0] == json.loads(json.dumps(handler.processed))
    assert "_id" not in handler.processed
    assert "_rev" not in handler.processed


def test_couchdb_stores_record_time_in_utc(couchdb_backend, record_time):
    from logbook.ticketing import TicketingHandler

    backend, database = couchdb_backend
    handler = TicketingHandler("http://example.invalid/", backend=backend)
    record = logbook.LogRecord("test", logbook.WARNING, "event")
    record.heavy_init()
    record.time = record_time(datetime(2020, 1, 2, 3, 4, 5, 17, tzinfo=timezone.utc))
    handler.emit(record)

    assert database.documents[0]["time"] == "2020-01-02T03:04:05.000017Z"
