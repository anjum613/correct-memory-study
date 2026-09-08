# Frozen source procedure: X26

Write a fixed-layout response into scratch storage and transmit the complete record including reserved areas.

Source-valid assumption: Fresh scratch storage initializes every unwritten byte to the public reserved value.

Target change: The same allocator interface can return reused storage containing prior data.
