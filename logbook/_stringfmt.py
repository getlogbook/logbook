# -*- coding: utf-8 -*-
"""
    logbook._stringfmt
    ~~~~~~~~~~~~~~~~~~

    Advanced string formatting for Python >= 2.4.
    This is a stripped version of 'stringformat', available at
     * http://pypi.python.org/pypi/StringFormat

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl, Florent Xicluna.
    :license: BSD, see LICENSE for more details.
"""
import re
import datetime

if hasattr(str, 'partition'):
    def partition(s, sep):
        return s.partition(sep)
else:   # Python 2.4
    def partition(s, sep):
        try:
            left, right = s.split(sep, 1)
        except ValueError:
            return s, '', ''
        return left, sep, right

_integer_classes = (int, long)
_date_classes = (datetime.datetime, datetime.date, datetime.time)
_format_str_re = re.compile(
    r'((?<!{)(?:{{)+'                       # '{{'
    r'|(?:}})+(?!})'                        # '}}
    r'|{(?:[^{](?:[^{}]+|{[^{}]*})*)?})'    # replacement field
)
_format_sub_re = re.compile(r'({[^{}]*})')  # nested replacement field
_format_spec_re = re.compile(
    r'((?:[^{}]?[<>=^])?)'      # alignment
    r'([-+ ]?)'                 # sign
    r'(#?)' r'(\d*)' r'(,?)'    # base prefix, minimal width, thousands sep
    r'((?:\.\d+)?)'             # precision
    r'(.?)$'                    # type
)
_field_part_re = re.compile(
    r'(?:(\[)|\.|^)'            # start or '.' or '['
    r'((?(1)[^]]*|[^.[]*))'     # part
    r'(?(1)(?:\]|$)([^.[]+)?)'  # ']' and invalid tail
)

if hasattr(re, '__version__'):
    _format_str_sub = _format_str_re.sub
else:
    # Python 2.4 fails to preserve the Unicode type
    def _format_str_sub(repl, s):
        if isinstance(s, unicode):
            return unicode(_format_str_re.sub(repl, s))
        return _format_str_re.sub(repl, s)


def _strformat(value, format_spec=""):
    """Internal string formatter.

    It implements the Format Specification Mini-Language.
    """
    m = _format_spec_re.match(str(format_spec))
    if not m:
        raise ValueError('Invalid conversion specification')
    align, sign, prefix, width, comma, precision, conversion = m.groups()
    is_numeric = hasattr(value, '__float__')
    is_integer = is_numeric and isinstance(value, _integer_classes)
    if is_numeric and conversion == 'n':
        # Default to 'd' for ints and 'g' for floats
        conversion = is_integer and 'd' or 'g'
    if conversion == 'c':
        conversion = 's'
        value = chr(value % 256)
    rv = ('%' + prefix + precision + (conversion or 's')) % (value,)
    if sign not in '-' and value >= 0:
        # sign in (' ', '+')
        rv = sign + rv
    if width:
        zero = (width[0] == '0')
        width = int(width)
    else:
        zero = False
        width = 0
    # Fastpath when alignment is not required
    if width <= len(rv):
        return rv
    fill, align = align[:-1], align[-1:]
    if not fill:
        fill = zero and '0' or ' '
    if align == '^':
        padding = width - len(rv)
        # tweak the formatting if the padding is odd
        if padding % 2:
            rv += fill
        rv = rv.center(width, fill)
    elif align == '=' or (zero and not align):
        if value < 0 or sign not in '-':
            rv = rv[0] + rv[1:].rjust(width - 1, fill)
        else:
            rv = rv.rjust(width, fill)
    elif align in ('>', '=') or (is_numeric and not align):
        # numeric value right aligned by default
        rv = rv.rjust(width, fill)
    else:
        rv = rv.ljust(width, fill)
    return rv


def _format_field(value, parts, conv, spec):
    """Format a replacement field."""
    for k, part, _ in parts:
        if k:
            if part.isdigit():
                value = value[int(part)]
            else:
                value = value[part]
        else:
            value = getattr(value, part)
    if conv:
        value = ((conv == 'r') and '%r' or '%s') % (value,)
    if hasattr(value, '__format__'):
        value = value.__format__(spec)
    elif isinstance(value, _date_classes) and spec:
        value = value.strftime(str(spec))
    else:
        value = _strformat(value, spec)
    return value


class FormattableString(object):
    """Class which implements method format().

    The method format() behaves like str.format() in python 2.6+.

    >>> FormattableString(u'{a:5}').format(a=42)
    ... # Same as u'{a:5}'.format(a=42)
    u'   42'

    """

    __slots__ = '_index', '_kwords', '_nested', '_string', 'format_string'

    def __init__(self, format_string):
        self._index = 0
        self._kwords = {}
        self._nested = {}

        self.format_string = format_string
        self._string = _format_str_sub(self._prepare, format_string)

    def __eq__(self, other):
        if isinstance(other, FormattableString):
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
        field, _, format_spec = partition(repl, ':')
        literal, sep, conversion = partition(field, '!')
        name_parts = _field_part_re.findall(literal)
        if literal[:1] in '.[':
            # Auto-numbering
            name = str(self._index)
            self._index += 1
            if not literal:
                del name_parts[0]
        else:
            name = name_parts.pop(0)[1]
            if name.isdigit() and self._index is not None:
                # Manual specification
                self._index = None
        if '{' in format_spec:
            format_spec = _format_sub_re.sub(self._prepare, format_spec)
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
