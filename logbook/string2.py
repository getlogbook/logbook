# -*- coding: utf-8 -*-
"""
    logbook.string2
    ~~~~~~~~~~~~~~~

    String formatting for Python 2.5.
    This is an implementation of the new string formatting (PEP 3101).

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl, Florent Xicluna.
    :license: BSD, see LICENSE for more details.
"""

import re

FORMAT_STR = re.compile(
    r'((?<!{)(?:{{)+'                       # '{{'
    r'|(?:}})+(?!})'                        # '}}
    r'|{(?:[^{](?:[^{}]+|{[^{}]*})*)?})'    # replacement field
)
FORMAT_SUB = re.compile(r'({[^{}]*})')      # nested replacement field
FORMAT_SPEC = re.compile(
    r'((?:[^{}]?[<>=^])?)'      # alignment
    r'([-+ ]?)'                 # sign
    r'(#?)' r'(\d*)' r'(,?)'    # base prefix, minimal width, thousands sep
    r'((?:\.\d+)?)'             # precision
    r'([bcdefgnosxEFGX%]?)$'    # type
)
FIELD_PART = re.compile('((?:^|\.)[^[.]+|\[[^]]+\])')


def _strformat(value, format_spec=""):
    """Internal string formatter.

    It implements the Format Specification Mini-Language.

    TODO:
     - alignment option '='
     - thousand separator
    """
    m = FORMAT_SPEC.match(format_spec)
    if not m:
        raise ValueError('Invalid conversion specification')
    align, sign, prefix, width, comma, precision, conversion = m.groups()
    zero, width = (width and width[0] == '0'), int(width or 0)
    fill, align = (align[:-1] or ' '), align[-1:]
    if not align:
        # numeric value right aligned by default
        if hasattr(value, '__float__'):
            align = '>'
        else:
            align = '<'
    elif align == '^':
        value = str(value)
        padding = width - len(value)
        if padding > 0 and padding % 2:
            value += fill
        value = value.center(width, fill)
    elif align == '=':
        # TODO: '=' alignment
        pass
    if comma:
        # TODO: thousand separator
        pass
    if fill not in ' 0':
        if not isinstance(value, basestring):
            value = str(values)
        if align == '<':
            value = value.ljust(width, fill)
        else:
            value = value.rjust(width, fill)
    oldspec = (r'%%%(flags)s%(width)s%(precision)s%(type)s' % {
        'flags': ('#' if (prefix or zero) else '') +
                 ('-' if (align == '<') else '') +
                 ('0' if (fill == '0') else '') +
                 (sign if (sign != '-') else ''),
        'width': width,
        'precision': precision,
        'type': conversion or 's',
    })
    return oldspec % (value,)


def _format_field(value, parts, conv, spec):
    """Format a replacement field."""
    for part in parts:
        if part.startswith('.'):
            value = getattr(value, part[1:])
        else:
            key = part[1:-1]
            if key.isdigit():
                value = value[int(key)]
            else:
                value = value[key]
    if conv:
        value = ('%r' if (conv == 'r') else '%s') % (value,)
    if hasattr(value, '__format__'):
        value = value.__format__(spec)
    elif hasattr(value, 'strftime') and spec:
        value = value.strftime(str(spec))
    else:
        value = _strformat(value, spec)
    return value


class Formatter(object):
    """Class which implements method format().

    The method format() behaves like str.format() in python 2.6+.

    >>> Formatter(u'{a:5}').format(a=42)    # Same as u'{a:5}'.format(a=42)
    u'   42'

    """

    __slots__ = '_index', '_kwords', '_nested', '_string', 'format_string'

    def __init__(self, format_string):
        self._index = 0
        self._kwords = {}
        self._nested = {}

        self.format_string = format_string
        self._string = FORMAT_STR.sub(self._prepare, format_string)

    def __eq__(self, other):
        if isinstance(other, Formatter):
            return self.format_string == other.format_string
        # Compare equal with the original string.
        return self.format_string == other

    def _prepare(self, match):
        # Called for each replacement field.
        part = match.group(0)
        if part[0] == part[-1]:
            # '{{' or '}}'
            assert part == part[0] * len(part)
            return part[:len(part) // 2]
        repl = part[1:-1]
        field, _, format_spec = repl.partition(':')

        literal, _, conversion = field.partition('!')
        name_parts = FIELD_PART.findall(literal)
        if not name_parts or name_parts[0].startswith(('.', '[')):
            name = ''
        else:
            name = name_parts.pop(0)
        if not name:
            # Auto-numbering
            if self._index is None:
                raise ValueError(
                    'cannot switch from manual field specification '
                    'to automatic field numbering')
            name = str(self._index)
            self._index += 1
        elif name.isdigit() and self._index is not None:
            # Manual specification
            if self._index:
                raise ValueError(
                    'cannot switch from automatic field numbering '
                    'to manual field specification')
            self._index = None
        if '{' in format_spec:
            format_spec = FORMAT_SUB.sub(self._prepare, format_spec)
            rv = (name_parts, conversion, format_spec)
            self._nested.setdefault(name, []).append(rv)
        else:
            rv = (name_parts, conversion, format_spec)
            self._kwords.setdefault(name, []).append(rv)
        return r'%%(%s)s' % id(rv)

    def format(self, *args, **kwargs):
        """Same as str.format() and unicode.format() in Python 2.6+."""
        if args:
            kwargs.update(dict((str(i), value)
                               for (i, value) in enumerate(args)))
        params = {}
        for name, items in self._kwords.items():
            value = kwargs[name]
            for item in items:
                parts, conv, spec = item
                params[str(id(item))] = _format_field(value, parts, conv, spec)
        for name, items in self._nested.items():
            value = kwargs[name]
            for item in items:
                parts, conv, spec = item
                spec = spec % params
                params[str(id(item))] = _format_field(value, parts, conv, spec)
        return self._string % params
