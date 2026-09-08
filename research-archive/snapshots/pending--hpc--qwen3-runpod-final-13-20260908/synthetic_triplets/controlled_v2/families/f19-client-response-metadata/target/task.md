Add optional `client_metadata` to `apply_metadata`. Clients use the documented
display headers `X-Label` and `X-Color`. Apply them in addition to the generated
request id and private cache policy, and return the same response.
