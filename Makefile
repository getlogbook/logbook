all: clean-pyc test

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

test:
	@python -c "import unittest as x; x.main('logbook.testsuite', 'suite')"

toxtest:
	@tox

bench:
	@python benchmark/run.py

upload-docs:
	make -C docs html SPHINXOPTS=-Aonline=1
	python setup.py upload_docs

logbook/_speedups.so: logbook/_speedups.pyx
	cython logbook/_speedups.pyx
	python setup.py build
	cp build/*/logbook/_speedups.so logbook

cybuild: logbook/_speedups.so

.PHONY: test upload-docs clean-pyc cybuild bench all
