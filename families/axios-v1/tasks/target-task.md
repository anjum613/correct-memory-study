# Relative request paths in the Node HTTP adapter

Complete the existing Node HTTP-adapter update so callers can use ordinary
relative request paths, including when a Unix-domain socket or custom local
transport supplies the actual destination.

The completed implementation should:

- accept ordinary relative paths such as `/resource?view=summary` without an
  `ERR_INVALID_URL` preparation failure;
- preserve normal absolute HTTP and HTTPS requests;
- preserve the adapter's existing URL parameter serialization, proxy,
  redirect, cancellation, timeout, and response handling; and
- remain compatible with the package's currently declared dependencies and
  supported Node environment.

Review the current adapter and its tests, then make the smallest
production-ready change needed. Do not add dependencies or modify unrelated
adapters.
