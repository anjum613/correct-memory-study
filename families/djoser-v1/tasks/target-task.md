# Configurable login validation completion

Finish the existing login-validation work so token login supports the
configured `LOGIN_FIELD`, including deployments that use email instead of the
user model's default username field.

The completed implementation should:

- accept correct credentials supplied through the configured login field;
- issue a token only for an active authenticated user;
- reject wrong passwords, unknown identities, inactive users, and malformed
  credential input;
- preserve the established default-username login behavior; and
- keep the change focused in the token serializer and covered by deterministic
  local tests.

Review the current serializer, settings, changelog, and visible token-login
tests, then make the smallest production-ready change. Use only dependencies
already declared by the project.
