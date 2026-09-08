Add an optional `base_url` for integrations. Resolve the existing relative
reference against it when supplied, or against `config.default_base` otherwise,
then return the transport response.
