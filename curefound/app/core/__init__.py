"""Cross-cutting infrastructure: config, logging, exceptions, lifespan, paths.

Nothing in this subpackage knows about Disease / Drug / Symptom -- that's the
domain folders' job. Keep it that way; domain imports FROM core, never the
other way around.
"""
