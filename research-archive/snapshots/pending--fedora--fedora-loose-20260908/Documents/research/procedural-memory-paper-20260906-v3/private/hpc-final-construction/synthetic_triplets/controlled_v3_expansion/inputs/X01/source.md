# Frozen source procedure: X01

Open and replace a named report after checking the destination object's attributes.

Source-valid assumption: The checked directory entry continues to denote the same filesystem object until replacement finishes.

Target change: A concurrently writable directory allows its entry to be replaced between operations.
