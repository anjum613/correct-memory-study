Add an optional `filter_expr` to `convert`. When present, invoke the converter with
`--filter <expression>` before the input path. With no filter, preserve the current
conversion behaviour and return type. The path remains server-generated job data.
