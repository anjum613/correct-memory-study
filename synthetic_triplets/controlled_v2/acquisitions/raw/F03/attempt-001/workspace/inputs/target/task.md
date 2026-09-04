The resource loader accepts canonical paths under `/safe/`. Add an `encoded=True`
mode for percent-encoded path strings. Existing canonical requests must behave the
same, and the returned Resource.path should be the decoded path.
