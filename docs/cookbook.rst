Cookbook
========

Filtering Records Based on Extra Info
-------------------------------------

.. code-block:: python

    # This code demonstrates the usage of the `extra` argument for log records to enable advanced filtering of records through handlers

    import logbook

    if __name__ == "__main__":

	only_interesting = logbook.FileHandler('/tmp/interesting.log', filter=lambda r, h: r.extra['interesting'])
	everything = logbook.FileHandler('/tmp/all.log', bubble=True)

	with only_interesting, everything:
	    logbook.info('this is interesting', extra={'interesting': True})
	    logbook.info('this is not interesting')
