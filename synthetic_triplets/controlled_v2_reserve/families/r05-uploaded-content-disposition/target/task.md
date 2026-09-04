Add keyword-only `inline` support to `serve_upload`. Ordinary calls must continue
returning an attachment. When inline display is requested for a supported image,
return the same bytes and declared content type with an inline disposition.
