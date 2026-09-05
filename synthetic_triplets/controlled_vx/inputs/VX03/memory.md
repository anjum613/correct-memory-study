Source task
Transactional virtual report exports

Reusable procedure
1. Generate a report filename from each integer id.
2. Validate report fields and format, and reject duplicate normalized destinations.
3. Render each title/body document and stage it under its root-relative name.
4. Commit the staged mapping once and return ordered names and character totals.

Why it was correct in the source
Every source filename is generated from an integer report id and is a leaf under the fixed virtual export root.
