# Static saved evidence, version 2

This package accompanies the saved analysis. It contains 624 record JSON files and 13 family JSON files. All 624 saved implementations, patches and task prompts are available; 623 records preserve a visible native trace. The one absent trace is recorded as unavailable, with no replacement or invented continuation.

The JSON files contain text for inspection. No saved candidate, security witness or evaluated agent is executed by the package. The original evidence is untouched. `COVERAGE.json` gives per-record hashes, byte counts and availability. Stable R identifiers join to `data/outcomes.csv` and `data/measurement_components.csv`.

Each record contains the delivered task/context, chronological visible assistant/tool items, final implementation, patch, and saved original component observations. The outcome table separately preserves original and corrected labels. An invalid record's raw Boolean fields are not automatically observed security outcomes. Only explicitly completed components enter the measurement sidecar.

Each family contains task and memory records, initial and reference implementation text, workspace instructions, and supporting fixture API text. Memory strings retain the original neutral padding. The reported 4,096-byte envelope includes delimiters; the stored between-delimiter byte count is smaller. Memory SHA-256 values support exact comparison with the saved source. No hidden security input, sealed executable witness, or evaluator reproduction command is included. Observer contracts, version hashes and reference observations accompany the analysis package.

Personal paths, accounts, hostnames and session identifiers are masked. Explicit model labels inside trace text are masked, while declared configuration labels remain available in the outcome table. Provider/system metadata and encrypted reasoning are excluded. Public tool feedback is retained. These transformations preserve visible behavior needed to assess the paper but are not a byte-identical native session export.

The frozen 52-packet annotation sample is also supplied. It was prepared before labeling, with model names and final scores withheld, and contains exact event/line anchors for the separate annotation outputs. The source procedure shown to annotators may differ from the memory delivered to the experimental agent, as explained in the codebook. Packet hashes and labels remain unchanged after annotation.

The package enables saved-evidence inspection and statistical reproduction, not independent rerunning of the historical security evaluations. It conveys no inferred license for unrelated third-party repository material.
