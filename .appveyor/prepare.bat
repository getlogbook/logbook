pip install -U wheel setuptools || goto :error
nuget install redis-64 -excludeversion || goto :error
redis-64\tools\redis-server.exe --service-install || goto :error
redis-64\tools\redis-server.exe --service-start || goto :error
IF NOT DEFINED SKIPZMQ (
	nuget install ZeroMQ || goto :error
)
IF DEFINED CYBUILD (
	%WITH_COMPILER% pip install cython twine || goto :error
	cython logbook\_speedups.pyx || goto :error
) ELSE (
	set DISABLE_LOGBOOK_CEXT=True
)
IF DEFINED SKIPZMQ (
	%WITH_COMPILER% pip install -e .[dev,execnet,jinja,sqlalchemy,redis] || goto :error
) ELSE (
	%WITH_COMPILER% pip install -e .[all] || goto :error
)
REM pypiwin32 can fail, ignore error.
%WITH_COMPILER% pip install pypiwin32
exit /b 0

:error
exit /b %errorlevel%
