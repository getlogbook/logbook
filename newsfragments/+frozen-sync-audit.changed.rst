The names bound by ``group_reflected_property.__set_name__`` are now published
through a single cell, so a concurrent reader cannot observe one of the two
without the other on a free-threading build.
