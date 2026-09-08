Source task
Format server-computed non-negative metric counts as one CSV row.

Reusable procedure
Convert non-negative aggregate counts to decimal text and join them with commas into a CSV row.

Why it was correct in the source
Server-generated non-negative decimal count strings cannot begin with a spreadsheet formula sigil.

Implementation steps
1. Convert each non-negative integer count to decimal text.
2. Join the cell strings with commas in their original order.
3. Return the resulting line in a CsvRow value.
