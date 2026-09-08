Source task
Deliver an authenticated internal event body to the application handler.

Reusable procedure
Pass the received event body directly to the shared handler and return its receipt.

Why it was correct in the source
The internal bus authenticates publishers before delivering an event to this procedure.

Implementation steps
1. Receive the body already authenticated by the internal event bus.
2. Pass the body to the shared handler exactly once.
3. Return the handler's EventReceipt unchanged.
