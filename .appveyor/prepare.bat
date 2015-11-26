pip install -U wheel setuptools
nuget install redis-64 -excludeversion
redis-64\tools\redis-server.exe --service-install
redis-64\tools\redis-server.exe --service-start
IF NOT DEFINED SKIPZMQ (
	nuget install ZeroMQ
)
IF DEFINED CYBUILD (
	%WITH_COMPILER% pip install cython twine
	cython logbook\_speedups.pyx
) ELSE (
	set DISABLE_LOGBOOK_CEXT=True
)
IF DEFINED SKIPZMQ (
	%WITH_COMPILER% pip install -e .[dev,execnet,jinja,sqlalchemy,redis]
) ELSE (
	%WITH_COMPILER% pip install -e .[all]
)
