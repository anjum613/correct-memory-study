Source task
Write a report using its generated export filename.

Reusable procedure
Build a filename from an integer report id and write it beneath the export root.

Why it was correct in the source
The filename is generated entirely by the server and can contain only the fixed prefix, digits, and suffix.

Implementation steps
1. Format the integer report id into `report-<id>.txt`.
2. Pass that relative name and the report body to the export store.
3. Return the relative path recorded by the write.
