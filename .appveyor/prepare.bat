pip install wheel
nuget install redis-64 -excludeversion
redis-64\redis-server.exe --service-install
redis-64\redis-server.exe --service-start
nuget install ZeroMQ
%WITH_COMPILER% pip install cython redis pyzmq
python scripts\test_setup.py
python setup.py develop
IF DEFINED CYBUILD (
	cython logbook\_speedups.pyx
	%WITH_COMPILER% python setup.py build
	pip install twine
)