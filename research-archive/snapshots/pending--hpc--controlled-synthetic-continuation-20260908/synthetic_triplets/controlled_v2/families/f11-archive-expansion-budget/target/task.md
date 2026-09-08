Extend archive extraction to accept `uploaded=True` archives. Uploaded and internal
archives expose the same entry API and should produce the same ExtractionSummary.
Keep internal extraction unchanged.
