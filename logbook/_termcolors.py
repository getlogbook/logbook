# -*- coding: utf-8 -*-
"""
    logbook._termcolors
    ~~~~~~~~~~~~~~~~~~~

    Provides terminal color mappings.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

esc = "\x1b["

codes = {}
codes[""]          = ""
codes["reset"]     = esc + "39;49;00m"

dark_colors  = ["black", "darkred", "darkgreen", "brown", "darkblue",
                "purple", "teal", "lightgray"]
light_colors = ["darkgray", "red", "green", "yellow", "blue",
                "fuchsia", "turquoise", "white"]

x = 30
for d, l in zip(dark_colors, light_colors):
    codes[d] = esc + "%im" % x
    codes[l] = esc + "%i;01m" % x
    x += 1

del d, l, x

codes["darkteal"]   = codes["turquoise"]
codes["darkyellow"] = codes["brown"]
codes["fuscia"]     = codes["fuchsia"]


def _str_to_type(obj, strtype):
    """Helper for ansiformat and colorize"""
    if isinstance(obj, type(strtype)):
        return obj
    return obj.encode('ascii')


def colorize(color_key, text):
    """Returns an ANSI formatted text with the given color."""
    return _str_to_type(codes[color_key], text) + text + \
           _str_to_type(codes["reset"], text)
