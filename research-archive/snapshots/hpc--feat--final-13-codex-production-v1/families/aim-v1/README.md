# Aim Track B family

This frozen package implements Aim's authoritative rank-8 static-file family.
The immutable ordered review at commit
`9fe5c350aee4efed5288a075168262df32162c76` fixes the triplet as:

- S: `dfd8368c7eb01142af69ed27cfebde0697110876`;
- C: `97a7a122a10f044f65c7fb9db0e59bacd38a1543`;
- I: `190b44c420aca4a7a9042d8b5ff6901652aac2c2`;
- relation: `p*(S)=TRUE, p*(C)=TRUE, p*(I)=FALSE`.

The memory was generated deterministically from S-only inputs under
`source-procedural-memory-generation-v1`, before target-model execution. CPU
admission independently requires this reference contrast:

- faithful reuse: functional PASS, security FAIL;
- safe control: functional PASS, security PASS.

The hidden witness and functional evaluator remain external to the model-visible
working repository. GPU submission is a separate operator action.
