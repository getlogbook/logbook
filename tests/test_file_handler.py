import gzip
import os
import time
from datetime import datetime

import brotli
import pytest

import logbook

from .utils import LETTERS, capturing_stderr_context


def test_file_handler(logfile, activation_strategy, logger):
    handler = logbook.FileHandler(
        logfile,
        format_string="{record.level_name}:{record.channel}:{record.message}",
    )
    with activation_strategy(handler):
        logger.warn("warning message")
    handler.close()
    with open(logfile) as f:
        assert f.readline() == "WARNING:testlogger:warning message\n"


def test_file_handler_unicode(logfile, activation_strategy, logger):
    with capturing_stderr_context() as captured:
        with activation_strategy(logbook.FileHandler(logfile)):
            logger.info("\u0431")
    assert not captured.getvalue()


def test_file_handler_delay(logfile, activation_strategy, logger):
    handler = logbook.FileHandler(
        logfile,
        format_string="{record.level_name}:{record.channel}:{record.message}",
        delay=True,
    )
    assert not os.path.isfile(logfile)
    with activation_strategy(handler):
        logger.warn("warning message")
    handler.close()

    with open(logfile) as f:
        assert f.readline() == "WARNING:testlogger:warning message\n"


def test_monitoring_file_handler(logfile, activation_strategy, logger):
    if os.name == "nt":
        pytest.skip("unsupported on windows due to different IO (also unneeded)")
    handler = logbook.MonitoringFileHandler(
        logfile,
        format_string="{record.level_name}:{record.channel}:{record.message}",
        delay=True,
    )
    with activation_strategy(handler):
        logger.warn("warning message")
        os.rename(logfile, os.fspath(logfile) + ".old")
        logger.warn("another warning message")
    handler.close()
    with open(logfile) as f:
        assert f.read().strip() == "WARNING:testlogger:another warning message"


def test_custom_formatter(activation_strategy, logfile, logger):
    def custom_format(record, handler):
        return record.level_name + ":" + record.message

    handler = logbook.FileHandler(logfile)
    with activation_strategy(handler):
        handler.formatter = custom_format
        logger.warn("Custom formatters are awesome")

    with open(logfile) as f:
        assert f.readline() == "WARNING:Custom formatters are awesome\n"


def test_rotating_file_handler(logfile, activation_strategy, logger):
    basename = os.path.basename(logfile)
    handler = logbook.RotatingFileHandler(
        logfile,
        max_size=2048,
        backup_count=3,
    )
    handler.format_string = "{record.message}"
    with activation_strategy(handler):
        for c, x in zip(LETTERS, range(32)):
            logger.warn(c * 256)
    files = [x for x in os.listdir(os.path.dirname(logfile)) if x.startswith(basename)]
    files.sort()

    assert files == [basename, basename + ".1", basename + ".2", basename + ".3"]
    with open(logfile) as f:
        assert f.readline().rstrip() == ("C" * 256)
        assert f.readline().rstrip() == ("D" * 256)
        assert f.readline().rstrip() == ("E" * 256)
        assert f.readline().rstrip() == ("F" * 256)


@pytest.mark.parametrize("backup_count", [1, 3])
def test_timed_rotating_file_handler(tmpdir, activation_strategy, backup_count):
    basename = str(tmpdir.join("trot.log"))
    handler = logbook.TimedRotatingFileHandler(basename, backup_count=backup_count)
    handler.format_string = "[{record.time:%H:%M}] {record.message}"

    def fake_record(message, year, month, day, hour=0, minute=0, second=0):
        lr = logbook.LogRecord("Test Logger", logbook.WARNING, message)
        lr.time = datetime(year, month, day, hour, minute, second)
        return lr

    with activation_strategy(handler):
        for x in range(10):
            handler.handle(fake_record("First One", 2010, 1, 5, x + 1))
        for x in range(20):
            handler.handle(fake_record("Second One", 2010, 1, 6, x + 1))
        for x in range(10):
            handler.handle(fake_record("Third One", 2010, 1, 7, x + 1))
        for x in range(20):
            handler.handle(fake_record("Last One", 2010, 1, 8, x + 1))

    files = sorted(x for x in os.listdir(str(tmpdir)) if x.startswith("trot"))

    assert files == [f"trot-2010-01-0{i}.log" for i in range(5, 9)][-backup_count:]
    with open(str(tmpdir.join("trot-2010-01-08.log"))) as f:
        assert f.readline().rstrip() == "[01:00] Last One"
        assert f.readline().rstrip() == "[02:00] Last One"
    if backup_count > 1:
        with open(str(tmpdir.join("trot-2010-01-07.log"))) as f:
            assert f.readline().rstrip() == "[01:00] Third One"
            assert f.readline().rstrip() == "[02:00] Third One"


@pytest.mark.parametrize("backup_count", [1, 3])
def test_timed_rotating_file_handler__rollover_format(
    tmpdir, activation_strategy, backup_count
):
    basename = str(tmpdir.join("trot.log"))
    handler = logbook.TimedRotatingFileHandler(
        basename,
        backup_count=backup_count,
        rollover_format="{basename}{ext}.{timestamp}",
    )
    handler.format_string = "[{record.time:%H:%M}] {record.message}"

    def fake_record(message, year, month, day, hour=0, minute=0, second=0):
        lr = logbook.LogRecord("Test Logger", logbook.WARNING, message)
        lr.time = datetime(year, month, day, hour, minute, second)
        return lr

    with activation_strategy(handler):
        for x in range(10):
            handler.handle(fake_record("First One", 2010, 1, 5, x + 1))
        for x in range(20):
            handler.handle(fake_record("Second One", 2010, 1, 6, x + 1))
        for x in range(10):
            handler.handle(fake_record("Third One", 2010, 1, 7, x + 1))
        for x in range(20):
            handler.handle(fake_record("Last One", 2010, 1, 8, x + 1))

    files = sorted(x for x in os.listdir(str(tmpdir)) if x.startswith("trot"))

    assert files == [f"trot.log.2010-01-0{i}" for i in range(5, 9)][-backup_count:]
    with open(str(tmpdir.join("trot.log.2010-01-08"))) as f:
        assert f.readline().rstrip() == "[01:00] Last One"
        assert f.readline().rstrip() == "[02:00] Last One"
    if backup_count > 1:
        with open(str(tmpdir.join("trot.log.2010-01-07"))) as f:
            assert f.readline().rstrip() == "[01:00] Third One"
            assert f.readline().rstrip() == "[02:00] Third One"


@pytest.mark.parametrize("backup_count", [1, 3])
@pytest.mark.parametrize("preexisting_file", [True, False])
def test_timed_rotating_file_handler__not_timed_filename_for_current(
    tmpdir, activation_strategy, backup_count, preexisting_file
):
    basename = str(tmpdir.join("trot.log"))

    if preexisting_file:
        with open(basename, "w") as file:
            file.write("contents")
        jan_first = time.mktime(datetime(2010, 1, 1).timetuple())
        os.utime(basename, (jan_first, jan_first))

    handler = logbook.TimedRotatingFileHandler(
        basename,
        format_string="[{record.time:%H:%M}] {record.message}",
        backup_count=backup_count,
        rollover_format="{basename}{ext}.{timestamp}",
        timed_filename_for_current=False,
    )

    def fake_record(message, year, month, day, hour=0, minute=0, second=0):
        lr = logbook.LogRecord("Test Logger", logbook.WARNING, message)
        lr.time = datetime(year, month, day, hour, minute, second)
        return lr

    with activation_strategy(handler):
        for x in range(10):
            handler.handle(fake_record("First One", 2010, 1, 5, x + 1))
        for x in range(20):
            handler.handle(fake_record("Second One", 2010, 1, 6, x + 1))
        for x in range(10):
            handler.handle(fake_record("Third One", 2010, 1, 7, x + 1))
        for x in range(20):
            handler.handle(fake_record("Last One", 2010, 1, 8, x + 1))

    computed_files = [x for x in os.listdir(str(tmpdir)) if x.startswith("trot")]

    expected_files = ["trot.log.2010-01-01"] if preexisting_file else []
    expected_files += [f"trot.log.2010-01-0{i}" for i in range(5, 8)]
    expected_files += ["trot.log"]
    expected_files = expected_files[-backup_count:]

    assert sorted(computed_files) == sorted(expected_files)

    with open(str(tmpdir.join("trot.log"))) as f:
        assert f.readline().rstrip() == "[01:00] Last One"
        assert f.readline().rstrip() == "[02:00] Last One"
    if backup_count > 1:
        with open(str(tmpdir.join("trot.log.2010-01-07"))) as f:
            assert f.readline().rstrip() == "[01:00] Third One"
            assert f.readline().rstrip() == "[02:00] Third One"


def _decompress(input_file_name, use_gzip=True):
    if use_gzip:
        with gzip.open(input_file_name, "rb") as in_f:
            return in_f.read().decode()
    else:
        with open(input_file_name, "rb") as in_f:
            return brotli.decompress(in_f.read()).decode()


@pytest.mark.parametrize("use_gzip", [True, False])
def test_compression_file_handler(logfile, activation_strategy, logger, use_gzip):
    handler = (
        logbook.GZIPCompressionHandler(logfile)
        if use_gzip
        else logbook.BrotliCompressionHandler(logfile)
    )
    handler.format_string = "{record.level_name}:{record.channel}:{record.message}"
    with activation_strategy(handler):
        logger.warn("warning message")
    handler.close()
    assert _decompress(logfile, use_gzip) == "WARNING:testlogger:warning message\n"
