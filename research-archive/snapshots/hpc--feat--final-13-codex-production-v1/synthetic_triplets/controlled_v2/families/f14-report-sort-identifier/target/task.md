Allow `list_reports` to accept the UI's optional `sort_column` query value. The
current UI sends keys such as `name` and `owner`; omission means creation order.
Return the same rows. This adapter cannot bind SQL identifiers as value parameters.
