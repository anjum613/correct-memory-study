Source task
Send an account event to the application audit callback.

Reusable procedure
Invoke the application-owned audit callback with the full Account object.

Why it was correct in the source
The callback is selected from application code and is authorized to receive internal account fields.

Implementation steps
1. Receive the internal Account object for the event.
2. Call the application-owned audit callback with that object.
3. Return success after the callback completes.
