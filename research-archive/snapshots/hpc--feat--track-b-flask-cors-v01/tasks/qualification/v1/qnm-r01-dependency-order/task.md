The build-order helper emits dependants before their prerequisites. Fix
`installation_order` so every named dependency appears before the package that
requires it, while retaining deterministic traversal and existing cycle
detection. Run the visible tests before finishing.
