import os
import sys

try:
    from thread import get_ident
except ImportError:
    from _thread import get_ident

import logbook
import pytest
from logbook.helpers import xrange

from .utils import require_module

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith(".pyc"):
    __file_without_pyc__ = __file_without_pyc__[:-1]

python_version = sys.version_info[:2]


@pytest.mark.xfail(
    os.name == 'nt' and (python_version == (3, 2) or python_version == (3, 3)),
    reason='Problem with in-memory sqlite on Python 3.2, 3.3 and Windows')
@require_module('sqlalchemy')
def test_basic_ticketing(logger):
    from logbook.ticketing import TicketingHandler
    from time import sleep
    with TicketingHandler('sqlite:///') as handler:
        for x in xrange(5):
            logger.warn('A warning')
            sleep(0.2)
            logger.info('An error')
            sleep(0.2)
            if x < 2:
                try:
                    1 / 0
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

    occurrences = handler.db.get_occurrences(tickets[2].ticket_id,
                                             order_by='time')
    assert len(occurrences) == 2
    record = occurrences[0]
    assert __file_without_pyc__ in record.filename
    # avoid 2to3 destroying our assertion
    assert getattr(record, 'func_name') == 'test_basic_ticketing'
    assert record.level == logbook.ERROR
    assert record.thread == get_ident()
    assert record.process == os.getpid()
    assert record.channel == 'testlogger'
    assert '1 / 0' in record.formatted_exception
