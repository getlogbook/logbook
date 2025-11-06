"""
logbook.notifiers
~~~~~~~~~~~~~~~~~

System notify handlers for OSX and Linux.

:copyright: (c) 2010 by Armin Ronacher, Christopher Grebs.
:license: BSD, see LICENSE for more details.
"""

from http import client as http_client
from urllib.parse import urlencode

from logbook.base import NOTSET
from logbook.handlers import Handler, LimitingHandlerMixin
from logbook.helpers import get_application_name


class NotificationBaseHandler(Handler, LimitingHandlerMixin):
    """Baseclass for notification handlers."""

    def __init__(
        self,
        application_name=None,
        record_limit=None,
        record_delta=None,
        level=NOTSET,
        filter=None,
        bubble=False,
    ):
        Handler.__init__(self, level, filter, bubble)
        LimitingHandlerMixin.__init__(self, record_limit, record_delta)
        if application_name is None:
            application_name = get_application_name()
        self.application_name = application_name

    def make_title(self, record):
        """Called to get the title from the record."""
        return f"{record.channel}: {record.level_name.title()}"

    def make_text(self, record):
        """Called to get the text of the record."""
        return record.message


class PushoverHandler(NotificationBaseHandler):
    """Sends notifications to pushover.net.  Can be forwarded to your Desktop,
    iPhone, or other compatible device. If `priority` is not one of -2, -1, 0,
    or 1, it is set to 0 automatically.
    """

    def __init__(
        self,
        application_name=None,
        apikey=None,
        userkey=None,
        device=None,
        priority=0,
        sound=None,
        record_limit=None,
        record_delta=None,
        level=NOTSET,
        filter=None,
        bubble=False,
        max_title_len=100,
        max_message_len=512,
    ):
        super().__init__(None, record_limit, record_delta, level, filter, bubble)

        self.application_name = application_name
        self.apikey = apikey
        self.userkey = userkey
        self.device = device
        self.priority = priority
        self.sound = sound

        self.max_title_len = max_title_len
        self.max_message_len = max_message_len

        if self.application_name is None:
            self.title = None
        else:
            self.title = self._crop(self.application_name, self.max_title_len)

        if self.priority not in [-2, -1, 0, 1]:
            self.priority = 0

    def _crop(self, msg, max_len):
        if max_len is not None and max_len > 0 and len(msg) > max_len:
            return f"{msg[: max_len - 3]}..."
        else:
            return msg

    def emit(self, record):
        message = self._crop(record.message, self.max_message_len)

        body_dict = {
            "token": self.apikey,
            "user": self.userkey,
            "message": message,
            "priority": self.priority,
        }

        if self.title is not None:
            body_dict["title"] = self.title
        if self.device is not None:
            body_dict["device"] = self.device
        if self.sound is not None:
            body_dict["sound"] = self.sound

        body = urlencode(body_dict)
        con = http_client.HTTPSConnection("api.pushover.net")
        con.request("POST", "/1/messages.json", body=body)
        con.close()
