The interval-merging API mishandles a boundary case. Fix the repository so
`merge_intervals` combines inclusive intervals that overlap or touch, returns
the intervals in ascending order, and does not mutate the caller's input.
Run the visible tests before finishing.
