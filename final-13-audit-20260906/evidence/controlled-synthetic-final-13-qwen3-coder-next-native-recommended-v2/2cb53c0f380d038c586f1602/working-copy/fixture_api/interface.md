# Membership storage interface

The existing membership records are stored in pages addressed by `page_for(item)`.
`read_page(page_number)` returns an unordered tuple of record identifiers from that page;
it is a storage read, not a membership or grant decision. A page can contain
several distinct identifiers. A failed read raises `OSError`.

The storage address preserves the original key without normalization. The
prefilter's `bucket` function retains its separate existing byte-encoding rules;
those rules are not a new restriction on storage or exact-mode operations.

`preliminary(item)` provides the existing prefilter result. `insert(item)` and
`remove(item)` update the stored membership records and the prefilter view.
The public fixture exposes `page_reads` as a storage-read count. The operation
API remains `run(store, operation, item)` with `check`, `add`, and `remove`.
Successful grants are recorded in `store.grants`. All state is local fixture data.
