Source task
Set the attachment header for a generated job export.

Reusable procedure
Interpolate a generated CSV filename into a quoted Content-Disposition header.

Why it was correct in the source
The filename is built from an integer job id and fixed ASCII text, so it cannot contain header delimiters.

Implementation steps
1. Build `job-<id>.csv` from the integer job id.
2. Interpolate that filename into the quoted Content-Disposition value.
3. Set the response header and return the filename in a Download object.
