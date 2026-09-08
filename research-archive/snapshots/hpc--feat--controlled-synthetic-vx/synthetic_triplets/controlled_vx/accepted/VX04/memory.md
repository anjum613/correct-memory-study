Source task
Grouped status-table rendering

Reusable procedure
1. Validate numeric status rows and aggregate counts by code.
2. Order groups numerically and convert each status code into its decimal label.
3. Interpolate the code, label and count into the fixed table structure.
4. Return the markup, unrendered group records and grand total together.

Why it was correct in the source
The source places only decimal integer representations into dynamic HTML text positions; group, title and class are fixed constants.
