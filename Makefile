all: clean-pyc test

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

test:
	python setup.py test

upload-docs:
	make -C docs html SPHINXOPTS=-Aonline=1
	python setup.py upload_docs

cybuild:
	cython logbook/_speedups.pyx
	python setup.py build
	cp build/*/logbook/_speedups.so logbook

.PHONY: test upload-docs clean-pyc cybuild all
