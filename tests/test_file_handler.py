import gzip
import os
import time
from datetime import datetime, timezone

import pytest

import logbook

from .utils import LETTERS, capturing_stderr_context

try:
    import brotlicffi as brotli
except ImportError:
    try:
        import brotli
    except ImportError:
        brotli = None


def test_file_handler(logfile, activation_strategy, logger):
    handler = logbook.FileHandler(
        logfile,
        format_string="{record.level_name}:{record.channel}:{record.message}",
    )
    with activation_strategy(handler):
        logger.warning("warning message")
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
        logger.warning("warning message")
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
        logger.warning("warning message")
        os.rename(logfile, os.fspath(logfile) + ".old")
        logger.warning("another warning message")
    handler.close()
    with open(logfile) as f:
        assert f.read().strip() == "WARNING:testlogger:another warning message"


def test_custom_formatter(activation_strategy, logfile, logger):
    def custom_format(record, handler):
        return record.level_name + ":" + record.message

    handler = logbook.FileHandler(logfile)
    with activation_strategy(handler):
        handler.formatter = custom_format
        logger.warning("Custom formatters are awesome")

    with open(logfile) as f:
        assert f.readline() == "WARNING:Custom formatters are awesome\n"


@pytest.mark.parametrize("delay", [False, True])
@pytest.mark.parametrize("max_size", [5, len("oversized first record\n")])
@pytest.mark.parametrize("existing_backup", [False, True])
def test_rotating_file_handler_does_not_back_up_empty_file(
    tmp_path, logger, delay, max_size, existing_backup
):
    filename = tmp_path / "oversized.log"
    backup = tmp_path / "oversized.log.1"
    if existing_backup:
        backup.write_text("previous generation\n")
    with (
        logbook.RotatingFileHandler(
            filename,
            max_size=max_size,
            backup_count=1,
            delay=delay,
            format_string="{record.message}",
        ),
        logbook.Flags(errors="raise"),
    ):
        logger.info("oversized first record")
        expected = (
            ["oversized.log", "oversized.log.1"]
            if existing_backup
            else ["oversized.log"]
        )
        assert sorted(path.name for path in tmp_path.iterdir()) == expected
        if existing_backup:
            assert backup.read_text() == "previous generation\n"
        assert filename.read_text() == "oversized first record\n"
        logger.info("next")

    assert filename.read_text() == "next\n"
    assert (tmp_path / "oversized.log.1").read_text() == "oversized first record\n"


def test_rotating_file_handler(logfile, activation_strategy, logger):
    basename = os.path.basename(logfile)
    handler = logbook.RotatingFileHandler(
        logfile,
        max_size=2048,
        backup_count=3,
    )
    handler.format_string = "{record.message}"
    with activation_strategy(handler):
        for c, _ in zip(LETTERS, range(32)):
            logger.warning(c * 256)
    files = [x for x in os.listdir(os.path.dirname(logfile)) if x.startswith(basename)]
    files.sort()

    assert files == [basename, basename + ".1", basename + ".2", basename + ".3"]
    with open(logfile) as f:
        assert f.readline().rstrip() == ("C" * 256)
        assert f.readline().rstrip() == ("D" * 256)
        assert f.readline().rstrip() == ("E" * 256)
        assert f.readline().rstrip() == ("F" * 256)


@pytest.fixture
def started_in_2010(monkeypatch):
    # Timed handlers keep records from before they started in the current file.
    monkeypatch.setattr(logbook.base, "_datetime_factory", lambda: datetime(2010, 1, 1))


@pytest.mark.parametrize("backup_count", [1, 3])
def test_timed_rotating_file_handler(
    tmpdir, activation_strategy, backup_count, started_in_2010
):
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
    tmpdir, activation_strategy, backup_count, started_in_2010
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
    tmpdir, activation_strategy, backup_count, preexisting_file, started_in_2010
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


def test_gzip_file_handler(logfile, activation_strategy, logger):
    handler = logbook.GZIPCompressionHandler(logfile)
    handler.format_string = "{record.level_name}:{record.channel}:{record.message}"
    with activation_strategy(handler):
        logger.warning("warning message")
    handler.close()
    with gzip.open(logfile, "rb") as f:
        assert f.read().decode() == "WARNING:testlogger:warning message\n"


@pytest.mark.skipif(brotli is None, reason="brotli not installed")
def test_brotli_file_handler(logfile, activation_strategy, logger):
    handler = logbook.BrotliCompressionHandler(logfile)
    handler.format_string = "{record.level_name}:{record.channel}:{record.message}"
    with activation_strategy(handler):
        logger.warning("warning message")
    handler.close()
    with open(logfile, "rb") as in_f:
        assert (
            brotli.decompress(in_f.read()).decode()
            == "WARNING:testlogger:warning message\n"
        )


@pytest.mark.skipif(os.name == "nt", reason="Requires POSIX special files")
@pytest.mark.parametrize("special_file", ["null", "fifo"])
@pytest.mark.parametrize("timed", [False, True])
def test_rotation_preserves_special_files(tmp_path, special_file, timed):
    filename = tmp_path / "special.log"
    reader = None
    if special_file == "null":
        filename.symlink_to(os.devnull)
    else:
        os.mkfifo(filename)
        reader = os.open(filename, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if timed:
            handler = logbook.TimedRotatingFileHandler(
                filename,
                timed_filename_for_current=False,
                backup_count=1,
                format_string="{record.message}",
            )
        else:
            handler = logbook.RotatingFileHandler(
                filename,
                max_size=1,
                backup_count=1,
                format_string="{record.message}",
            )
        with handler, logbook.Flags(errors="raise"):
            for day in [1, 2]:
                record = logbook.LogRecord("test", logbook.INFO, f"message {day}")
                record.time = datetime(2020, 1, day)
                handler.handle(record)
        assert list(tmp_path.iterdir()) == [filename]
        if special_file == "null":
            assert filename.is_symlink()
            assert os.fspath(filename.resolve()) == os.path.realpath(os.devnull)
        else:
            assert filename.is_fifo()
            assert os.read(reader, 4096) == b"message 1\nmessage 2\n"
    finally:
        if reader is not None:
            os.close(reader)


def test_size_rollover_appends_to_new_file(tmp_path, logger):
    filename = tmp_path / "append.log"

    class InterleavedHandler(logbook.RotatingFileHandler):
        def write(self, item):
            if item == "rollover\n":
                with filename.open("a") as other_writer:
                    other_writer.write("external\n")
            super().write(item)

    with (
        InterleavedHandler(
            filename, max_size=12, backup_count=1, format_string="{record.message}"
        ),
        logbook.Flags(errors="raise"),
    ):
        logger.info("before")
        logger.info("rollover")

    assert (tmp_path / "append.log.1").read_text() == "before\n"
    assert filename.read_text() == "external\nrollover\n"


@pytest.mark.parametrize("timed_filename_for_current", [True, False])
def test_timed_rollover_keeps_late_record_in_current_file(
    tmp_path, timed_filename_for_current, started_in_2010
):
    handler = logbook.TimedRotatingFileHandler(
        tmp_path / "app.log",
        backup_count=2,
        timed_filename_for_current=timed_filename_for_current,
        format_string="{record.message}",
    )
    with handler, logbook.Flags(errors="raise"):
        for day, message in [(1, "first"), (2, "second"), (1, "late"), (2, "again")]:
            record = logbook.LogRecord("test", logbook.INFO, message)
            record.time = datetime(2010, 1, day)
            handler.handle(record)

    current = "app-2010-01-02.log" if timed_filename_for_current else "app.log"
    assert (tmp_path / current).read_text() == "second\nlate\nagain\n"
    assert (tmp_path / "app-2010-01-01.log").read_text() == "first\n"


def test_timed_rollover_keeps_record_from_before_start_in_current_file(
    tmp_path, monkeypatch
):
    (tmp_path / "app-2010-01-01.log").write_text("day 1\n")
    monkeypatch.setattr(
        logbook.base, "_datetime_factory", lambda: datetime(2010, 1, 2, 0, 10)
    )
    handler = logbook.TimedRotatingFileHandler(
        tmp_path / "app.log",
        timed_filename_for_current=False,
        format_string="{record.message}",
    )
    with handler, logbook.Flags(errors="raise"):
        for message, when in [
            ("late", datetime(2010, 1, 1, 23, 50)),
            ("day 2", datetime(2010, 1, 2, 0, 20)),
        ]:
            record = logbook.LogRecord("test", logbook.INFO, message)
            record.time = when
            handler.handle(record)

    assert (tmp_path / "app-2010-01-01.log").read_text() == "day 1\n"
    assert (tmp_path / "app.log").read_text() == "late\nday 2\n"


def test_timed_rollover_hourly_across_local_dst(tmp_path, monkeypatch):
    if hasattr(time, "tzset"):
        monkeypatch.setenv("TZ", "Europe/Berlin")
        time.tzset()
    monkeypatch.setattr(
        logbook.base, "_datetime_factory", lambda: datetime(2026, 3, 29)
    )
    try:
        handler = logbook.TimedRotatingFileHandler(
            tmp_path / "app.log",
            date_format="%Y-%m-%d-%H",
            format_string="{record.message}",
        )
        with handler, logbook.Flags(errors="raise"):
            for hour in range(5):
                record = logbook.LogRecord("test", logbook.INFO, str(hour))
                record.time = datetime(2026, 3, 29, hour, 30)
                handler.handle(record)
    finally:
        monkeypatch.undo()
        if hasattr(time, "tzset"):
            time.tzset()

    assert len(list(tmp_path.iterdir())) == 5


def test_timed_rollover_in_repeated_hour(tmp_path, monkeypatch, record_time):
    # Starts at 01:40 EDT; records at 01:50 EDT, then 01:10 and 01:20 EST.
    start, *times = [
        record_time(datetime(2026, 11, 1, hour, minute, tzinfo=timezone.utc))
        for hour, minute in [(5, 40), (5, 50), (6, 10), (6, 20)]
    ]
    monkeypatch.setattr(logbook.base, "_datetime_factory", lambda: start)
    handler = logbook.TimedRotatingFileHandler(
        tmp_path / "app.log", date_format="%H-%M", format_string="{record.message}"
    )
    with handler, logbook.Flags(errors="raise"):
        for t in times:
            record = logbook.LogRecord("test", logbook.INFO, f"{t:%H-%M}")
            record.time = t
            handler.handle(record)

    for t in times:
        assert (tmp_path / f"app-{t:%H-%M}.log").read_text() == f"{t:%H-%M}\n"


def test_timed_rollover_restart_keeps_backups(tmp_path, record_time):
    times = [
        record_time(datetime(2026, 7, 15, hour, 30, tzinfo=timezone.utc))
        for hour in (12, 13, 14)
    ]
    for t in times:
        (tmp_path / f"app-{t:%Y-%m-%d-%H}.log").touch()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(logbook.base, "_datetime_factory", lambda: times[-1])
        handler = logbook.TimedRotatingFileHandler(
            tmp_path / "app.log", date_format="%Y-%m-%d-%H", backup_count=3
        )
    with handler, logbook.Flags(errors="raise"):
        record = logbook.LogRecord("test", logbook.INFO, "restarted")
        record.time = times[-1]
        handler.handle(record)

    assert len(list(tmp_path.iterdir())) == 3
