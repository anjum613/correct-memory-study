Implement export_batch(reports, store, *, format_name='text'). Reports are
dicts with integer id, title string, body string, and optional name string.
Missing name uses report-<id>.txt. Names denote nonempty relative file names
in the virtual /exports namespace; nested names are supported. No operating
system files are used. Support text (title + newline + body) and upper
(the same document uppercased). Validate formats and fields, reject duplicate
effective destinations with ValueError, and commit no partial batch on any
rejected input. Destination equivalence uses the store's POSIX normalization.
Call store.commit exactly once on success, including empty input. Return
{paths: [original relative names], characters: [document lengths], total:
sum of lengths, count: report count}. Preserve input order and input objects.
Keep export_one(id, body, store) unchanged. Store semantics are fixed and
contain no symlinks, concurrent writers, permissions or filesystem effects.
