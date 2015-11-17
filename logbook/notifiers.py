# -*- coding: utf-8 -*-
"""
    logbook.notifiers
    ~~~~~~~~~~~~~~~~~

    System notify handlers for OSX and Linux.

    :copyright: (c) 2010 by Armin Ronacher, Christopher Grebs.
    :license: BSD, see LICENSE for more details.
"""
import os
import sys
import base64
from time import time

from logbook.base import NOTSET, ERROR, WARNING
from logbook.handlers import Handler, LimitingHandlerMixin
from logbook.helpers import get_application_name, PY2, http_client, u

if PY2:
    from urllib import urlencode
else:
    from urllib.parse import urlencode


def create_notification_handler(application_name=None, level=NOTSET,
                                icon=None):
    """Creates a handler perfectly fit the current platform.  On Linux
    systems this creates a :class:`LibNotifyHandler`, on OS X systems it
    will create a :class:`GrowlHandler`.
    """
    if sys.platform == 'darwin':
        return GrowlHandler(application_name, level=level, icon=icon)
    return LibNotifyHandler(application_name, level=level, icon=icon)


class NotificationBaseHandler(Handler, LimitingHandlerMixin):
    """Baseclass for notification handlers."""

    def __init__(self, application_name=None, record_limit=None,
                 record_delta=None, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        LimitingHandlerMixin.__init__(self, record_limit, record_delta)
        if application_name is None:
            application_name = get_application_name()
        self.application_name = application_name

    def make_title(self, record):
        """Called to get the title from the record."""
        return u('%s: %s') % (record.channel, record.level_name.title())

    def make_text(self, record):
        """Called to get the text of the record."""
        return record.message


class GrowlHandler(NotificationBaseHandler):
    """A handler that dispatches to Growl.  Requires that either growl-py or
    py-Growl are installed.
    """

    def __init__(self, application_name=None, icon=None, host=None,
                 password=None, record_limit=None, record_delta=None,
                 level=NOTSET, filter=None, bubble=False):
        NotificationBaseHandler.__init__(self, application_name, record_limit,
                                         record_delta, level, filter, bubble)

        # growl is using the deprecated md5 module, but we really don't need
        # to see that deprecation warning
        from warnings import filterwarnings
        filterwarnings(module='Growl', category=DeprecationWarning,
                       action='ignore')

        try:
            import Growl
            self._growl = Growl
        except ImportError:
            raise RuntimeError('The growl module is not available.  You have '
                               'to install either growl-py or py-Growl to '
                               'use the GrowlHandler.')

        if icon is not None:
            if not os.path.isfile(icon):
                raise IOError('Filename to an icon expected.')
            icon = self._growl.Image.imageFromPath(icon)
        else:
            try:
                icon = self._growl.Image.imageWithIconForCurrentApplication()
            except TypeError:
                icon = None

        self._notifier = self._growl.GrowlNotifier(
            applicationName=self.application_name,
            applicationIcon=icon,
            notifications=['Notset', 'Debug', 'Info', 'Notice', 'Warning',
                           'Error', 'Critical'],
            hostname=host,
            password=password
        )
        self._notifier.register()

    def is_sticky(self, record):
        """Returns `True` if the sticky flag should be set for this record.
        The default implementation marks errors and criticals sticky.
        """
        return record.level >= ERROR

    def get_priority(self, record):
        """Returns the priority flag for Growl.  Errors and criticals are
        get highest priority (2), warnings get higher priority (1) and the
        rest gets 0.  Growl allows values between -2 and 2.
        """
        if record.level >= ERROR:
            return 2
        elif record.level == WARNING:
            return 1
        return 0

    def emit(self, record):
        if not self.check_delivery(record)[1]:
            return
        self._notifier.notify(record.level_name.title(),
                              self.make_title(record),
                              self.make_text(record),
                              sticky=self.is_sticky(record),
                              priority=self.get_priority(record))


class LibNotifyHandler(NotificationBaseHandler):
    """A handler that dispatches to libnotify.  Requires pynotify installed.
    If `no_init` is set to `True` the initialization of libnotify is skipped.
    """

    def __init__(self, application_name=None, icon=None, no_init=False,
                 record_limit=None, record_delta=None, level=NOTSET,
                 filter=None, bubble=False):
        NotificationBaseHandler.__init__(self, application_name, record_limit,
                                         record_delta, level, filter, bubble)

        try:
            import pynotify
            self._pynotify = pynotify
        except ImportError:
            raise RuntimeError('The pynotify library is required for '
                               'the LibNotifyHandler.')

        self.icon = icon
        if not no_init:
            pynotify.init(self.application_name)

    def set_notifier_icon(self, notifier, icon):
        """Used to attach an icon on a notifier object."""
        try:
            from gtk import gdk
        except ImportError:
            # TODO: raise a warning?
            raise RuntimeError('The gtk.gdk module is required to set an icon.')

        if icon is not None:
            if not isinstance(icon, gdk.Pixbuf):
                icon = gdk.pixbuf_new_from_file(icon)
            notifier.set_icon_from_pixbuf(icon)

    def get_expires(self, record):
        """Returns either EXPIRES_DEFAULT or EXPIRES_NEVER for this record.
        The default implementation marks errors and criticals as EXPIRES_NEVER.
        """
        pn = self._pynotify
        return pn.EXPIRES_NEVER if record.level >= ERROR else pn.EXPIRES_DEFAULT

    def get_urgency(self, record):
        """Returns the urgency flag for pynotify.  Errors and criticals are
        get highest urgency (CRITICAL), warnings get higher priority (NORMAL)
        and the rest gets LOW.
        """
        pn = self._pynotify
        if record.level >= ERROR:
            return pn.URGENCY_CRITICAL
        elif record.level == WARNING:
            return pn.URGENCY_NORMAL
        return pn.URGENCY_LOW

    def emit(self, record):
        if not self.check_delivery(record)[1]:
            return
        notifier = self._pynotify.Notification(self.make_title(record),
                                               self.make_text(record))
        notifier.set_urgency(self.get_urgency(record))
        notifier.set_timeout(self.get_expires(record))
        self.set_notifier_icon(notifier, self.icon)
        notifier.show()


class BoxcarHandler(NotificationBaseHandler):
    """Sends notifications to boxcar.io.  Can be forwarded to your iPhone or
    other compatible device.
    """
    api_url = 'https://boxcar.io/notifications/'

    def __init__(self, email, password, record_limit=None, record_delta=None,
                 level=NOTSET, filter=None, bubble=False):
        NotificationBaseHandler.__init__(self, None, record_limit,
                                         record_delta, level, filter, bubble)
        self.email = email
        self.password = password

    def get_screen_name(self, record):
        """Returns the value of the screen name field."""
        return record.level_name.title()

    def emit(self, record):
        if not self.check_delivery(record)[1]:
            return
        body = urlencode({
            'notification[from_screen_name]':
                self.get_screen_name(record).encode('utf-8'),
            'notification[message]':
                self.make_text(record).encode('utf-8'),
            'notification[from_remote_service_id]': str(int(time() * 100))
        })
        con = http_client.HTTPSConnection('boxcar.io')
        con.request('POST', '/notifications/', headers={
            'Authorization': 'Basic ' +
            base64.b64encode((u('%s:%s') % (self.email, self.password))
                             .encode('utf-8')).strip(),
        }, body=body)
        con.close()


class NotifoHandler(NotificationBaseHandler):
    """Sends notifications to notifo.com.  Can be forwarded to your Desktop,
    iPhone, or other compatible device.
    """

    def __init__(self, application_name=None, username=None, secret=None,
                 record_limit=None, record_delta=None, level=NOTSET,
                 filter=None, bubble=False, hide_level=False):
        try:
            import notifo
        except ImportError:
            raise RuntimeError(
                'The notifo module is not available.  You have '
                'to install notifo to use the NotifoHandler.'
            )
        NotificationBaseHandler.__init__(self, None, record_limit,
                                         record_delta, level, filter, bubble)
        self._notifo = notifo
        self.application_name = application_name
        self.username = username
        self.secret = secret
        self.hide_level = hide_level

    def emit(self, record):

        if self.hide_level:
            _level_name = None
        else:
            _level_name = self.level_name

        self._notifo.send_notification(self.username, self.secret, None,
                                       record.message, self.application_name,
                                       _level_name, None)


class PushoverHandler(NotificationBaseHandler):
    """Sends notifications to pushover.net.  Can be forwarded to your Desktop,
    iPhone, or other compatible device. If `priority` is not one of -2, -1, 0,
    or 1, it is set to 0 automatically.
    """

    def __init__(self, application_name=None, apikey=None, userkey=None,
                 device=None, priority=0, sound=None, record_limit=None,
                 record_delta=None, level=NOTSET, filter=None, bubble=False):

        super(PushoverHandler, self).__init__(None, record_limit, record_delta,
                                              level, filter, bubble)

        self.application_name = application_name
        self.apikey = apikey
        self.userkey = userkey
        self.device = device
        self.priority = priority
        self.sound = sound

        if self.application_name is None:
            self.title = None
        elif len(self.application_name) > 100:
            self.title = "%s..." % (self.application_name[:-3],)
        else:
            self.title = self.application_name

        if self.priority not in [-2, -1, 0, 1]:
            self.priority = 0

    def emit(self, record):

        if len(record.message) > 512:
            message = "%s..." % (record.message[:-3],)
        else:
            message = record.message

        body_dict = {
            'token': self.apikey,
            'user': self.userkey,
            'message': message,
            'priority': self.priority
        }

        if self.title is not None:
            body_dict['title'] = self.title
        if self.device is not None:
            body_dict['device'] = self.device
        if self.sound is not None:
            body_dict['sound'] = self.sound

        body = urlencode(body_dict)
        con = http_client.HTTPSConnection('api.pushover.net')
        con.request('POST', '/1/messages.json', body=body)
        con.close()
