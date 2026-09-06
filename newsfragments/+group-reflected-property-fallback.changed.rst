``group_reflected_property`` no longer runs a full rich comparison when the
stored value is the same ``int`` object as the property's fallback, which is the
common case for :attr:`~logbook.Logger.level`. Logging calls are about 2%
faster.
