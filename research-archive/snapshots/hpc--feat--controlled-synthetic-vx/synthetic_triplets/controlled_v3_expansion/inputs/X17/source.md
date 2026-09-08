# Frozen source procedure: X17

Write all parts of a logical bundle and publish its active reference.

Source-valid assumption: The source transaction makes all bundle writes and reference publication visible atomically.

Target change: The same operation is resumed across stages whose commits become separately durable.
