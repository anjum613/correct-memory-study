Source task
Extract a bundle emitted by the bounded internal packager.

Reusable procedure
Read every archive entry, write its expanded bytes, and accumulate the extraction summary.

Why it was correct in the source
The internal bundle producer enforces the expansion budget before the archive reaches this procedure.

Implementation steps
1. Iterate through the bundle entries in order.
2. Read each entry fully and write its body under the entry name.
3. Accumulate file count and expanded bytes for the summary.
