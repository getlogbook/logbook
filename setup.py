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

import sys
from setuptools import setup, Extension, Feature
from distutils.command.build_ext import build_ext
from distutils.errors import CCompilerError, DistutilsExecError, \
    DistutilsPlatformError


class BuildFailed(Exception):
    pass


cmdclass = {}
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
speedups = Feature('optional C speed-enhancement module', standard=True,
                   ext_modules=[Extension('logbook._speedups',
                                          ['logbook/_speedups.c'])])


def run_setup(with_binary):
    features = {}
    if with_binary:
        features['speedups'] = speedups
    setup(
        name='Logbook',
        version='0.2',
        license='BSD',
        url='http://logbook.pocoo.org/',
        author='Armin Ronacher, Georg Brandl',
        author_email='armin.ronacher@active-4.com',
        description='A logging replacement for Python',
        long_description=__doc__,
        packages=['logbook'],
        zip_safe=False,
        platforms='any',
        tests_require='''
            SQLAlchemy>=0.6

        ''',
        test_suite='test_logbook',
        cmdclass=cmdclass,
        features=features
    )


def echo(msg=''):
    sys.stdout.write(msg + '\n')


try:
    run_setup(True)
except BuildFailed:
    LINE = '=' * 74
    BUILD_EXT_WARNING = 'WARNING: The C extension could not be compiled, speedups are not enabled.'

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
