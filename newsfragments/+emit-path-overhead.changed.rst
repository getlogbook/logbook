StreamHandler.flush now reads its stream once and resolves the stream's flush
method once per call, reducing the overhead of writing records.
