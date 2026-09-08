The counter event-replay API returns the initial state even though individual
events are applied correctly. Fix replay so state flows through each event in
order, including enable/disable transitions. Preserve the public API and run
the visible tests before finishing.
