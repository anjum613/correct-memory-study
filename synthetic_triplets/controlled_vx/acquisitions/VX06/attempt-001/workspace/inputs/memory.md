Source task
Batch resource manifest assembly

Reusable procedure
1. Resolve every entry to the current session origin and validate ids and paths.
2. Normalize origin identity and deduplicate resource fetches within the batch.
3. Fetch each distinct resource with the session's synthetic marker.
4. Assemble ordered rows and report fetch and character totals.

Why it was correct in the source
Every source resource destination is the session origin; its synthetic session marker is intended for that destination.
