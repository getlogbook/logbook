r"""
Logbook
-------

An awesome logging implementation that is fun to use.

Quickstart
``````````

::

    from logbook import Logger
    log = Logger('A Fancy Name')

    log.warn('Logbook is too awesome for most applications')
    log.error("Can't touch this")

Works for web apps too
``````````````````````

::

    from logbook import MailHandler, Processor

    mailhandler = MailHandler(from_addr='servererror@example.com',
                              recipients=['admin@example.com'],
                              level='ERROR', format_string=u'''\
    Subject: Application Error for {record.extra[path]} [{record.extra[method]}]

    Message type:       {record.level_name}
    Location:           {record.filename}:{record.lineno}
    Module:             {record.module}
    Function:           {record.func_name}
    Time:               {record.time:%Y-%m-%d %H:%M:%S}
    Remote IP:          {record.extra[ip]}
    Request:            {record.extra[path]} [{record.extra[method]}]

    Message:

    {record.message}
    ''')

    def handle_request(request):
        def inject_extra(record, handler):
            record.extra['ip'] = request.remote_addr
            record.extra['method'] = request.method
            record.extra['path'] = request.path

        with Processor(inject_extra):
            with mailhandler:
                # execute code that might fail in the context of the
                # request.
"""

import os
import sys
from setuptools import setup, Extension, Feature
from distutils.command.build_ext import build_ext
from distutils.errors import CCompilerError, DistutilsExecError, \
    DistutilsPlatformError


extra = {}
cmdclass = {}


class BuildFailed(Exception):
    pass


ext_errors = (CCompilerError, DistutilsExecError, DistutilsPlatformError)
if sys.platform == 'win32' and sys.version_info > (2, 6):
    # 2.6's distutils.msvc9compiler can raise an IOError when failing to
    # find the compiler
    ext_errors += (IOError,)


class ve_build_ext(build_ext):
    """This class allows C extension building to fail."""

    def run(self):
        try:
            build_ext.run(self)
        except DistutilsPlatformError:
            raise BuildFailed()

    def build_extension(self, ext):
        try:
            build_ext.build_extension(self, ext)
        except ext_errors:
            raise BuildFailed()

cmdclass['build_ext'] = ve_build_ext
# Don't try to compile the extension if we're running on PyPy
if os.path.isfile('logbook/_speedups.c') and not hasattr(sys, "pypy_translation_info"):
    speedups = Feature('optional C speed-enhancement module', standard=True,
                       ext_modules=[Extension('logbook._speedups',
                                              ['logbook/_speedups.c'])])
else:
    speedups = None


def run_setup(with_binary):
    features = {}
    if with_binary and speedups is not None:
        features['speedups'] = speedups
    setup(
        name='Logbook',
        version='0.11.0',
        license='BSD',
        url='http://logbook.pocoo.org/',
        author='Armin Ronacher, Georg Brandl',
        author_email='armin.ronacher@active-4.com',
        description='A logging replacement for Python',
        long_description=__doc__,
        packages=['logbook'],
        zip_safe=False,
        platforms='any',
        cmdclass=cmdclass,
        features=features,
        install_requires=[
        ],
        **extra
    )


def echo(msg=''):
    sys.stdout.write(msg + '\n')


try:
    run_setup(True)
except BuildFailed:
    LINE = '=' * 74
    BUILD_EXT_WARNING = ('WARNING: The C extension could not be compiled, '
                         'speedups are not enabled.')

    echo(LINE)
    echo(BUILD_EXT_WARNING)
    echo('Failure information, if any, is above.')
    echo('Retrying the build without the C extension now.')
    echo()

    run_setup(False)

    echo(LINE)
    echo(BUILD_EXT_WARNING)
    echo('Plain-Python installation succeeded.')
    echo(LINE)
