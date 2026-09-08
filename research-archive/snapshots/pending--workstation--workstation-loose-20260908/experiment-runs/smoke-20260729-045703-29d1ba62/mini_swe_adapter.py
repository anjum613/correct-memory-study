import logging
import os
from pathlib import Path

import yaml
from minisweagent import __version__, package_dir
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.litellm_model import LitellmModel

repository = Path(os.environ["CMPILOT_REPOSITORY"])
task = Path(os.environ["CMPILOT_TASK_FILE"]).read_text(encoding="utf-8")
trajectory = Path(os.environ["CMPILOT_TRAJECTORY"])
agent_config = yaml.safe_load((Path(package_dir) / "config" / "default.yaml").read_text(encoding="utf-8"))["agent"]
agent_config["output_path"] = trajectory

logging.basicConfig(level=logging.INFO)
model = LitellmModel(
    model_name="openai/" + os.environ["CMPILOT_MODEL"],
    model_kwargs={
        "api_base": os.environ["CMPILOT_BASE_URL"],
        "api_key": "local-smoke-placeholder",
        "temperature": 0,
        "drop_params": True,
    },
    cost_tracking="ignore_errors",
)
agent = DefaultAgent(model, LocalEnvironment(cwd=str(repository)), **agent_config)
print("mini-SWE-agent version: " + __version__)
agent.run(task)
