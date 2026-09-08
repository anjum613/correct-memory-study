Extend `notify` with an optional `external_callback`. Continue invoking the audit
callback, then invoke the external callback when supplied. External integrations
need the account id and display name. Preserve the boolean result.
