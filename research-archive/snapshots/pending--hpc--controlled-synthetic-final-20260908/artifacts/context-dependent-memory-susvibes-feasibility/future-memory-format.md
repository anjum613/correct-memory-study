# Future Memory Format

Status: schema and rendering design only; no confirmatory packet is populated.

```text
<SOURCE_TASK>
real source task/request
</SOURCE_TASK>

<SOURCE_IMPLEMENTATION>
exact source implementation or patch
</SOURCE_IMPLEMENTATION>

<SOURCE_VALIDATION>
existing source test command and passing result
</SOURCE_VALIDATION>
```

The packet must contain exact source evidence, not researcher advice. It must never include the target vulnerability, target security fix, proof of vulnerability, future target history, CVE/GHSA identifier, a warning that assumptions changed, or a researcher-written explanation of p*.

Relevant and irrelevant packets will eventually use this identical format and be matched on language, tokenizer length, implementation size, source-test evidence, and approximate source-task complexity. No packet is constructed in this feasibility task.

