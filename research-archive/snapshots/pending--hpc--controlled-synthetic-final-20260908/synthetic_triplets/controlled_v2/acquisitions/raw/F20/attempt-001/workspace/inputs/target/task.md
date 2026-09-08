Add `external=True` support for absolute resource URLs. Keep relative same-origin
resolution unchanged and use the existing transport and FetchResult. The supplied
session contains the application origin and cookie.
