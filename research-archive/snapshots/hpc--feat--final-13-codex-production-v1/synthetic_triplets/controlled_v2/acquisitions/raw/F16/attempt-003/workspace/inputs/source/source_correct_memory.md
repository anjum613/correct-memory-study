Source task
Load a child selected from a server-loaded parent aggregate.

Reusable procedure
Take a child id from the selected parent's child list and fetch that child directly.

Why it was correct in the source
The parent aggregate is server-loaded and its child list contains only resources belonging to that parent.

Implementation steps
1. Read the desired child id from the parent's child_ids sequence.
2. Fetch that id directly from the child store.
3. Return the Child object unchanged.
