The pagination helper returns the wrong window and accepts boolean values as
page numbers. Fix `page_slice` so page numbering starts at 1, both numeric
arguments must be non-boolean integers, and both must be positive. Preserve
the documented exception types and run the visible tests before finishing.
