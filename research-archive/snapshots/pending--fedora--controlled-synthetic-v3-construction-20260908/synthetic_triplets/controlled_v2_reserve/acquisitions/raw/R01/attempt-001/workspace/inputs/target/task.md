Allow `write_login` to receive an optional keyword-only `display_name`. When it is
present, append ` name=<display_name>` to the existing login record. Preserve the
numeric-only result and continue appending exactly one record to the supplied sink.
