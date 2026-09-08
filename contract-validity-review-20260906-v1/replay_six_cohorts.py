"""Optional reproduction of the final six-cohort offline replay, never agents.

Writes to a new output directory; preserves the original review logs. This
entrypoint enforces the 6 September 2026 scope amendment.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import json

import replay as frozen_driver

ROOT = Path(__file__).resolve().parent
MODELS = {'GPT55', 'Luna', 'Terra', 'QwenNext', 'Qwen30', 'Devstral'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory for independent replay logs')
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists(), 'Use a new output directory to preserve prior results'
    frozen_driver.verify_freeze()
    receipt = frozen_driver.read(ROOT / 'SCOPE_AMENDMENT_RECEIPT.json')
    assert frozen_driver.digest(ROOT / 'six_cohort_review_census.json') == receipt['six_cohort_census_sha256']
    assert frozen_driver.read(ROOT / 'validation_summary.json')['passed']
    correction = frozen_driver.read(ROOT / 'CORRECTION_FREEZE.json')
    assert frozen_driver.digest(ROOT / 'review_worker.py') == correction['worker_sha256']
    suite = ROOT / 'evaluator-correction-v1/synthetic_triplets/controlled_v3_executable_oracle_release_v1/researcher_tests/shared/sealed_suite.py'
    assert frozen_driver.digest(suite) == correction['corrected_suite_sha256']
    census = frozen_driver.read(ROOT / 'six_cohort_review_census.json')
    assert len(census) == 144 and {r['model'] for r in census} == MODELS
    output.mkdir(parents=True)

    def one(row):
        workspace = Path(row['copied_workspace'])
        assert frozen_driver.digest(workspace / 'app/service.py') == row['service_sha256']
        values = {version: frozen_driver.call(version, 'candidate', row['family'], workspace,
                    output / row['run_id'] / (version + '.json')) for version in frozen_driver.VERSIONS}
        return {'run_id': row['run_id'], 'model': row['model'], 'results': values}

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, census))
    frozen_driver.save(output / 'six_cohort_replay_results.json', results)
    print(json.dumps({'saved_submissions':len(results), 'agent_executions':0, 'output':str(output)}))


if __name__ == '__main__':
    main()
