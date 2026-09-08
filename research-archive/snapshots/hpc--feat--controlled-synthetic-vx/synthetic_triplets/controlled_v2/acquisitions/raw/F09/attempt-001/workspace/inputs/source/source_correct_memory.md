Source task
Reserve a unique service name during single-threaded startup.

Reusable procedure
Check that a name is absent, then put the owner into the registry and return a reservation.

Why it was correct in the source
Startup registration is single-threaded, so no other writer can act between the check and put.

Implementation steps
1. Check whether the requested name already exists in the registry.
2. Raise a duplicate-name error if it exists.
3. Otherwise put the owner and return its Reservation.
