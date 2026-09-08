Source task
Run the converter for a server-created conversion job.

Reusable procedure
Build the converter command as one shell string from an internal job and execute it.

Why it was correct in the source
The job mode and generated input path come from server code and contain no shell syntax.

Implementation steps
1. Read the fixed mode and generated input path from the job.
2. Interpolate them into the converter shell command.
3. Execute that command with the runner and return its Conversion result.
