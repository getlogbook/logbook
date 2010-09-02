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

from setuptools import setup

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
)
