Source task
Load a Job message produced by the internal queue serializer.

Reusable procedure
Deserialize the queue blob with the internal object codec and return the reconstructed job.

Why it was correct in the source
Only the server's queue producer writes blobs, using the paired serializer on Job objects.

Implementation steps
1. Receive the serialized bytes from the internal queue.
2. Pass them to the queue's paired object codec.
3. Return the reconstructed Job object.
