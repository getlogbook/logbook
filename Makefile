test:
	python setup.py test

upload_docs:
	make -C docs html SPHINXOPTS=-Aonline=1
	python setup.py upload_docs

cybuild:
	cython logbook/_speedups.pyx
	python setup.py build
	cp build/*/logbook/_speedups.so logbook

.PHONY: test upload_docs
