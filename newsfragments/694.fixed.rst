Closing a RedisHandler now stops its background flushing thread and flushes the
remaining records without racing the worker.
