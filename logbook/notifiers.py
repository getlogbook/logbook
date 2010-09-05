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

from logbook.base import NOTSET, ERROR, WARNING
from logbook.handlers import Handler
from logbook.helpers import get_application_name


def create_notification_handler(application_name=None, level=NOTSET, icon=None):
    """Creates a handler perfectly fit the current platform.  On Linux
    systems this creates a :class:`LibNotifyHandler`, on OS X systems it
    will create a :class:`GrowlHandler`.
    """
    if os.platform == 'darwin':
        return GrowlHandler(application_name, level=level, icon=icon)
    return LibNotifyHandler(application_name, level=level, icon=icon)


class GrowlHandler(Handler):
    """A handler that dispatches to Growl.  Requires that either growl-py or
    py-Growl are installed.
    """

    def __init__(self, application_name=None, icon=None, host=None,
                 password=None, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)

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

        # if no application name is provided, guess it from the executable
        if application_name is None:
            application_name = get_application_name()

        if icon is not None:
            if not os.path.isfile(icon):
                raise IOError('Filename to an icon expected.')
            icon = self._growl.Image.imageFromPath(icon)
        else:
            try:
                icon = self._growl.Image.imageWithIconForCurrentApplication()
            except TypeError:
                icon = None

        self.application_name = application_name
        self._notifier = self._growl.GrowlNotifier(
            applicationName=application_name,
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

    def make_title(self, record):
        """Called to get the title from the record."""
        return u'%s: %s' % (record.channel, record.level_name.title())

    def make_text(self, record):
        """Called to get the text of the record."""
        return record.message

    def emit(self, record):
        title = self.make_title(record)
        text = self.make_text(record)
        self._notifier.notify(record.level_name.title(), title, text,
                              sticky=self.is_sticky(record),
                              priority=self.get_priority(record))


class LibNotifyHandler(Handler):
    """A handler that dispatches to libnotify.  Requires pynotify installed.
    If `no_init` is set to `True` the initialization of libnotify is skipped.
    """

    def __init__(self, application_name=None, icon=None, no_init=False, level=NOTSET,
                 filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)

        try:
            import pynotify
            self._pynotify = pynotify
        except ImportError:
            raise RuntimeError('The pynotify library is required for '
                               'the LibNotifyHandler.')

        if application_name is None:
            application_name = get_application_name()
        self.application_name = application_name
        self.icon = icon
        if not self.no_init:
            pynotify.init(application_name)

    def set_icon(self, notifier, icon):
        try:
            from gtk import gdk
        except ImportError:
            #TODO: raise a warning?
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
            return pn.URGENCY_CIRITICAL
        elif record.level == WARNING:
            return pn.URGENCY_NORMAL
        return pn.URGENCY_LOW

    def make_summary(self, record):
        """Called to get the summary from the record."""
        return u'%s: %s' % (record.channel, record.level_name.title())

    def make_body(self, record):
        """Called to get the body of the record."""
        return record.message

    def emit(self, record):
        summary = self.make_summary(record)
        body = self.make_body(record)
        notifier = self._pynotify.Notification(summary, body)
        notifier.set_urgency(self.get_urgency(record))
        notifier.set_timeout(self.get_expires(record))
        self.set_icon(notifier, self.icon)
        notifier.show()
