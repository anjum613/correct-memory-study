#!/usr/bin/env python3
from __future__ import annotations
import copy, hashlib, http.client, json, os, platform, subprocess, sys, traceback
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
import yaml
from minisweagent import __version__ as MINI_SWE_VERSION
from minisweagent.models.litellm_model import LitellmModel
from minisweagent.models.utils.actions_toolcall import BASH_TOOL, format_toolcall_observation_messages

ROOT = Path(os.environ["PROTOCOL_ROOT"])
BASE_URL = "http://127.0.0.1:8000/v1"
MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
TEMPERATURE = 0
MAX_TOKENS = 256
TOOLS = [copy.deepcopy(BASH_TOOL)]
FORCED_BASH = {"type": "function", "function": {"name": "bash"}}
CONFIG_PATH = Path("/mnt/data/anjum/mini-swe-env/lib/python3.11/site-packages/minisweagent/config/default.yaml")
TASK = "For this non-evaluated diagnostic, inspect the current directory by requesting exactly one bash tool call with the command pwd. Do not modify files."

def now() -> str:
    return datetime.now(UTC).isoformat()

def js(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

def dist(name: str) -> str | None:
    try: return version(name)
    except PackageNotFoundError: return None

def post_once(body: bytes) -> tuple[int | None, dict[str, str], bytes, str | None]:
    parsed = urlsplit(BASE_URL)
    try:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=120)
        conn.request("POST", parsed.path.rstrip("/") + "/chat/completions", body=body, headers={"Content-Type":"application/json","Accept":"application/json"})
        resp = conn.getresponse()
        raw = resp.read()
        status, headers = resp.status, {key.lower(): value for key, value in resp.getheaders()}
        conn.close()
        return status, headers, raw, None
    except Exception as exc:
        return None, {}, b"", f"{type(exc).__name__}: {exc}"

def fields(data: Any) -> dict[str, Any]:
    out = {"finish_reason":None, "content":None, "tool_calls":None, "usage":None, "function_calls":[], "tool_call_status":"response_unparseable"}
    if not isinstance(data, dict): return out
    out["usage"] = data.get("usage")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        out["tool_call_status"] = "response_missing_choice"; return out
    choice = choices[0]; out["finish_reason"] = choice.get("finish_reason")
    message = choice.get("message")
    if not isinstance(message, dict):
        out["tool_call_status"] = "response_missing_message"; return out
    out["content"] = message.get("content"); calls = message.get("tool_calls"); out["tool_calls"] = calls
    if calls is None or calls == []:
        out["tool_call_status"] = "no_tool_call"; return out
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict) or not isinstance(calls[0].get("function"), dict):
        out["tool_call_status"] = "malformed_tool_call"; return out
    call = calls[0]; fun = call["function"]; raw_args = fun.get("arguments"); parsed_args = None; parse_error = None
    if not isinstance(raw_args, str):
        parse_error = "function.arguments is not a string"
    else:
        try: parsed_args = json.loads(raw_args)
        except Exception as exc: parse_error = f"{type(exc).__name__}: {exc}"
    out["function_calls"] = [{"tool_call_id":call.get("id"),"type":call.get("type"),"function_name":fun.get("name"),"raw_arguments":raw_args,"parsed_arguments":parsed_args,"arguments_parse_error":parse_error}]
    if fun.get("name") == "bash" and isinstance(parsed_args, dict) and isinstance(parsed_args.get("command"), str) and parse_error is None:
        out["tool_call_status"] = "valid_native_bash_tool_call"
    else:
        out["tool_call_status"] = "malformed_tool_call"
    return out

def direct(probe: str, messages: list[dict[str, Any]], tool_choice: dict[str, Any] | None, purpose: str) -> tuple[dict[str, Any], Any]:
    payload: dict[str, Any] = {"model":MODEL_ID,"messages":messages,"tools":TOOLS,"temperature":TEMPERATURE,"max_tokens":MAX_TOKENS,"stream":False}
    choice_mode = "unset"
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice; choice_mode = "forced"
    request = js(payload); started = now()
    status, headers, raw, transport_error = post_once(request)
    finished = now(); parsed = None; parse_error = None
    if raw:
        try: parsed = json.loads(raw.decode("utf-8"))
        except Exception as exc: parse_error = f"{type(exc).__name__}: {exc}"
    elif transport_error is None: parse_error = "empty provider response"
    response_fields = fields(parsed)
    if transport_error: classification = "provider_transport_error"
    elif status != 200: classification = "provider_http_error"
    elif parse_error: classification = "provider_malformed_response"
    elif response_fields["tool_call_status"] == "valid_native_bash_tool_call": classification = "native_tool_call_returned_not_executed"
    elif response_fields["tool_call_status"] == "no_tool_call": classification = "model_no_tool_call"
    else: classification = "model_malformed_tool_call"
    record: dict[str, Any] = {
        "probe":probe, "purpose":purpose, "started_at_utc":started, "finished_at_utc":finished,
        "request":{"model_id":MODEL_ID,"temperature":TEMPERATURE,"max_tokens":MAX_TOKENS,"tool_choice_mode":choice_mode,"tool_choice":tool_choice,"tools_schema":TOOLS,"messages":messages,"request_file":"request.json","request_sha256":digest(request)},
        "response":{"http_status":status,"headers":headers,"transport_error":transport_error,"raw_response_file":"response.raw","response_sha256":digest(raw),"parsed_response":parsed,"response_parse_error":parse_error,**response_fields},
        "classification":classification,
        "command_execution":{"model_returned_command_executed":False,"reason":"native fields only; command execution prohibited for this probe"},
    }
    directory = ROOT / probe.lower(); directory.mkdir(exist_ok=False)
    (directory/"request.json").write_bytes(request); (directory/"response.raw").write_bytes(raw); save(directory/"record.json",record)
    return record, parsed

def production_messages() -> list[dict[str, str]]:
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment
    config = yaml.safe_load(CONFIG_PATH.read_text())["agent"]
    model = LitellmModel(model_name="openai/"+MODEL_ID, model_kwargs={"api_base":BASE_URL,"api_key":"local-protocol-placeholder","temperature":TEMPERATURE,"drop_params":True}, cost_tracking="ignore_errors")
    agent = DefaultAgent(model, LocalEnvironment(cwd=str(ROOT)), **config)
    agent.extra_template_vars = {"task":TASK}
    return [model.format_message(role="system",content=agent._render_template(agent.config.system_template)),model.format_message(role="user",content=agent._render_template(agent.config.instance_template))]

def fake_response(call: dict[str, Any]) -> Any:
    fun = call["function"]
    fake_call = SimpleNamespace(id=call.get("id"),type=call.get("type"),function=SimpleNamespace(name=fun.get("name"),arguments=fun.get("arguments")))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[fake_call]))])

def probe_d(messages: list[dict[str, Any]]) -> dict[str, Any]:
    record, _ = direct("D",messages,None,"production prompt; mini-SWE native parser and strict pwd-only execution")
    response = record["response"]; state = response["tool_call_status"]
    consumption: dict[str, Any] = {"mini_swe_received_valid_native_call":False,"mini_swe_consumed_call":False,"allowlist":["pwd"],"tool_executed":False}
    if state == "no_tool_call":
        record["classification"] = "model_no_tool_call"; consumption["reason"] = "model produced no tool call; mini-SWE consumption was not reached"
    elif state != "valid_native_bash_tool_call":
        record["classification"] = "model_malformed_tool_call"; consumption["reason"] = "model produced a malformed native tool call; mini-SWE consumption was not reached"
    else:
        consumption["mini_swe_received_valid_native_call"] = True
        try:
            adapter = LitellmModel(model_name="openai/"+MODEL_ID,model_kwargs={"api_base":BASE_URL,"api_key":"local-protocol-placeholder","drop_params":True},cost_tracking="ignore_errors")
            actions = adapter._parse_actions(fake_response(response["tool_calls"][0]))
            consumption["parsed_actions"] = actions; consumption["mini_swe_consumed_call"] = True
        except Exception as exc:
            record["classification"] = "agent_integration_failure"; consumption.update({"reason":"mini-SWE received a valid native call but failed to consume it","exception":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
        else:
            command = actions[0]["command"] if len(actions) == 1 and isinstance(actions[0],dict) else None
            consumption["requested_command"] = command
            if command != "pwd":
                record["classification"] = "command_not_allowlisted_not_executed"; consumption["reason"] = "valid native call requested a command outside the strict pwd allowlist"
            else:
                try:
                    result = subprocess.run(["pwd"],cwd=ROOT,text=True,capture_output=True,timeout=10,check=False)
                    output = {"output":result.stdout,"returncode":result.returncode,"exception_info":None}
                    consumption.update({"tool_executed":True,"execution":{"allowed":True,"executed_argv":["pwd"],"returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr}})
                    try:
                        consumption["formatted_observations"] = format_toolcall_observation_messages(actions=actions,outputs=[output],observation_template=adapter.config.observation_template)
                        record["classification"] = "tool_executed_and_mini_swe_consumed_native_call"
                    except Exception as exc:
                        record["classification"] = "tool_executed_agent_postprocess_failure"; consumption.update({"reason":"tool executed but mini-SWE failed afterward while formatting observation","exception":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
                except Exception as exc:
                    record["classification"] = "tool_execution_failure"; consumption.update({"reason":"the allowlisted pwd tool execution failed","exception":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
    record["command_execution"] = consumption
    save(ROOT/"d"/"record.json",record); save(ROOT/"d"/"mini_swe_consumption.json",consumption)
    return record

def main() -> None:
    if not ROOT.is_dir() : raise RuntimeError(f"artifact directory must exist and be empty: {ROOT}")
    (ROOT/"run_protocol.py").write_text(Path(__file__).read_text())
    production = production_messages()
    manifest: dict[str, Any] = {
        "study_type":"non_evaluated_protocol_qualification","started_at_utc":now(),
        "execution_policy":{"each_probe_model_request_count":1,"automatic_retries":False,"A_B_C_execute_model_commands":False,"D_command_allowlist":["pwd"]},
        "versions":{"python":sys.version,"mini_swe_agent":MINI_SWE_VERSION,"litellm":dist("litellm"),"openai":dist("openai"),"PyYAML":dist("PyYAML"),"pydantic":dist("pydantic"),"vllm_server_image":"/mnt/data/anjum/cmpilot/images/vllm-v0.6.6.post1.sif","model_id":MODEL_ID,"base_url":BASE_URL,"host":platform.node()},
        "probe_design":{"A":"forced native Bash function baseline","B":"production default Markdown-code-block prompt with native Bash schema and unset tool_choice","C":"minimal prompt with native Bash schema and unset tool_choice","D":"production prompt; native parser and pwd-only execution"},
        "production_prompt_source":str(CONFIG_PATH),"production_messages":production,
    }
    save(ROOT/"manifest.json",manifest)
    records = [
        direct("A",[{"role":"user","content":"Call the available bash function exactly once with the JSON argument {\"command\":\"pwd\"}. Do not provide prose."}],FORCED_BASH,"forced native Bash function baseline")[0],
        direct("B",production,None,"production default Markdown-code-block prompt conflict with native Bash schema")[0],
        direct("C",[{"role":"user","content":"Use the available bash tool to run pwd."}],None,"minimal voluntary native Bash tool selection")[0],
        probe_d(production),
    ]
    manifest["finished_at_utc"] = now()
    manifest["records"] = [{"probe":r["probe"],"classification":r["classification"],"http_status":r["response"]["http_status"],"finish_reason":r["response"]["finish_reason"],"usage":r["response"]["usage"],"tool_call_status":r["response"]["tool_call_status"],"request_sha256":r["request"]["request_sha256"],"response_sha256":r["response"]["response_sha256"]} for r in records]
    save(ROOT/"manifest.json",manifest)
    print(json.dumps({"artifact_directory":str(ROOT),"records":manifest["records"]},indent=2))
if __name__ == "__main__": main()
