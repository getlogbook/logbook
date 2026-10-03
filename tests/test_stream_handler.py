import io

import pytest

import logbook


@pytest.mark.parametrize("encoding", [None, "utf-8", "utf-16-le"])
def test_binary_stream_encoding(logger, encoding):
    stream = io.BytesIO()
    handler = logbook.StreamHandler(
        stream, encoding=encoding, format_string="{record.message}"
    )
    with handler:
        logger.info("snowman: \u2603")
    codec = encoding or "utf-8"
    assert stream.getvalue() == "snowman: \u2603\n".encode(codec)
    assert stream.getvalue().decode(codec) == "snowman: \u2603\n"


@pytest.mark.parametrize("encoding", [None, "ascii", "utf-16-le"])
def test_text_stream_ignores_handler_encoding(logger, encoding):
    stream = io.StringIO()
    with logbook.StreamHandler(
        stream, encoding=encoding, format_string="{record.message}"
    ):
        logger.info("snowman: \u2603")
    assert stream.getvalue() == "snowman: \u2603\n"


def test_binary_file_encoding(logger, tmp_path):
    path = tmp_path / "log"
    with path.open("wb") as stream:
        with logbook.StreamHandler(
            stream, encoding="utf-16-le", format_string="{record.message}"
        ):
            logger.info("snowman: \u2603")
    assert path.read_bytes() == "snowman: \u2603\n".encode("utf-16-le")
