#!/bin/bash
# Preserved excerpts from the controller-attested job-25517 script.
# The first command passed five literal plus operands to argparse.
"$CMPILOT_PYTHON" "$VERIFIER" +  --approved-root "$PRE" +  --manifest "$MANIFEST" +  --output "$ARTIFACT/runtime-input-verification.json" +  >"$ARTIFACT/runtime-input-verification.stdout" +  2>"$ARTIFACT/runtime-input-verification.stderr"

/usr/bin/env | /usr/bin/grep -E '^(SLURM_JOB_ID|SLURM_JOB_NAME|SLURM_JOB_NODELIST|SLURM_CPUS_PER_TASK|LANG|LC_ALL|PATH)=' +  >"$ARTIFACT/job-environment.txt"

"$CMPILOT_PYTHON" "$DRIVER" +  --artifact-dir "$ARTIFACT/gate" +  --cmpilot-python "$CMPILOT_PYTHON" +  --vllm-python "$VLLM_PYTHON" +  --project-root "$PROJECT" +  --source-fixture "$SOURCE_FIXTURE" +  --model-cache-root /home/s224049759/model-cache/huggingface +  --expected-environment-fingerprint 6afe3a785d3d96956e8eca1e57276637ac02f9793cbeb1fcc1955924f6277071 +  --expected-runtime-content-digest 5e640248ebe171e106707ad4aaca0eebf98673f5c4b10b87458364c6f300e9ee +  --expected-model-cache-digest dd0c2e60a213d49471d16e54ffc7a9eef89bbad87a01d56adf37a901419e9075 +  >"$ARTIFACT/driver.stdout" +  2>"$ARTIFACT/driver.stderr"
