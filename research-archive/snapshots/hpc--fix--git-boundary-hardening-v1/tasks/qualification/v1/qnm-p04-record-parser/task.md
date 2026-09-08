`parse_record` must decode semicolon-separated `key=value` fields used by the
public import API. Values may themselves contain `=`, surrounding whitespace
is ignored, and malformed, empty-key, or duplicate fields must raise
`ValueError`. Fix the parser and run the visible tests before finishing.
