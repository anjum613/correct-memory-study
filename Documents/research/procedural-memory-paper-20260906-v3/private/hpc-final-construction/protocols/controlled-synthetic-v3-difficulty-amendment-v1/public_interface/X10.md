# Media formats and delivery interface

`text/plain` uses the four-byte header `TXT` followed by a zero byte and a
nonempty body of bytes 32–126 or tab, line feed, and carriage return.
`image/x-local-pixels` uses `PIX` followed by a zero byte, one-byte nonzero width
and height, then exactly width times height times three pixel bytes.

Delivery accepts a mode, media type, filename and bytes. The public fixture
collects those arguments and the public checks verify ordinary supported content
and downloads. Its collection code is not the deployment's media renderer.
Filenames are strings and payloads are bytes; an invalid type returns `invalid`.
These format definitions describe the existing formats, not a new format policy.
