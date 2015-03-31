import logbook

from .utils import make_fake_mail_handler


def test_handler_filter_after_processor(activation_strategy, logger):
    handler = make_fake_mail_handler(format_string='''\
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
''',
                                     filter=lambda r, h: 'ip' in r.extra,
                                     bubble=False)

    class Request(object):
        remote_addr = '127.0.0.1'
        method = 'GET'
        path = '/index.html'

    def handle_request(request):
        def inject_extra(record):
            record.extra['ip'] = request.remote_addr
            record.extra['method'] = request.method
            record.extra['path'] = request.path

        processor = logbook.Processor(inject_extra)
        with activation_strategy(processor):
            handler.push_thread()
            try:
                try:
                    1 / 0
                except Exception:
                    logger.exception('Exception happened during request')
            finally:
                handler.pop_thread()

    handle_request(Request())
    assert len(handler.mails) == 1
    mail = handler.mails[0][2]
    assert 'Subject: Application Error for /index.html [GET]' in mail
    assert '1 / 0' in mail


def test_handler_processors(activation_strategy, logger):
    handler = make_fake_mail_handler(format_string='''\
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

    class Request(object):
        remote_addr = '127.0.0.1'
        method = 'GET'
        path = '/index.html'

    def handle_request(request):
        def inject_extra(record):
            record.extra['ip'] = request.remote_addr
            record.extra['method'] = request.method
            record.extra['path'] = request.path

        processor = logbook.Processor(inject_extra)
        with activation_strategy(processor):
            handler.push_thread()
            try:
                try:
                    1 / 0
                except Exception:
                    logger.exception('Exception happened during request')
            finally:
                handler.pop_thread()

    handle_request(Request())
    assert len(handler.mails) == 1
    mail = handler.mails[0][2]
    assert 'Subject: Application Error for /index.html [GET]' in mail
    assert '1 / 0' in mail
