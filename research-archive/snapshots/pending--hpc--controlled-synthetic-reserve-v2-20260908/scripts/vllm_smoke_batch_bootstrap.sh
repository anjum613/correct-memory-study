#!/usr/bin/env bash
# Shared non-interactive batch-shell bootstrap for the vLLM smoke tests.

vllm_smoke_bootstrap() {
    local artifact_dir="${1:?artifact directory is required}"
    local venv="${2:?virtual environment is required}"
    local preflight_log="$artifact_dir/batch-shell-preflight.txt"
    local module_list="$artifact_dir/module-list.txt"
    local conda_path=

    printf "preflight_started_at=%s\n" "$(date --iso-8601=seconds)" > "$preflight_log"
    printf "module_before_init=" >> "$preflight_log"
    command -v module >> "$preflight_log" 2>/dev/null || printf "unavailable\n" >> "$preflight_log"

    if ! command -v module >/dev/null 2>&1; then
        if [ ! -r /etc/profile.d/lmod.sh ]; then
            printf "ERROR: Lmod initialization file is unavailable: /etc/profile.d/lmod.sh\n" | tee -a "$preflight_log" >&2
            return 70
        fi
        printf "lmod_init_source=/etc/profile.d/lmod.sh\n" >> "$preflight_log"
        # The login shell sources this file to define the module function.
        # shellcheck disable=SC1091
        if ! source /etc/profile.d/lmod.sh; then
            printf "ERROR: failed to source /etc/profile.d/lmod.sh\n" | tee -a "$preflight_log" >&2
            return 70
        fi
    fi

    if ! command -v module >/dev/null 2>&1; then
        printf "ERROR: module remains unavailable after Lmod initialization\n" | tee -a "$preflight_log" >&2
        return 70
    fi
    printf "module_after_init=%s\n" "$(command -v module)" >> "$preflight_log"

    if ! conda_path=$(command -v conda); then
        printf "ERROR: conda is unavailable after batch-shell initialization\n" | tee -a "$preflight_log" >&2
        return 71
    fi
    printf "conda=%s\n" "$conda_path" >> "$preflight_log"

    if [ ! -d "$venv" ]; then
        printf "ERROR: vLLM environment directory is unavailable: %s\n" "$venv" | tee -a "$preflight_log" >&2
        return 72
    fi
    if [ ! -r "$venv/bin/activate" ] || [ ! -x "$venv/bin/python" ]; then
        printf "ERROR: vLLM environment activation files are unavailable: %s\n" "$venv" | tee -a "$preflight_log" >&2
        return 72
    fi
    printf "venv_directory=%s\n" "$venv" >> "$preflight_log"

    if ! module purge > "$module_list" 2>&1; then
        printf "ERROR: module purge failed after Lmod initialization\n" | tee -a "$preflight_log" >&2
        return 73
    fi
    if ! module list >> "$module_list" 2>&1; then
        printf "ERROR: module list failed after Lmod initialization\n" | tee -a "$preflight_log" >&2
        return 73
    fi

    # shellcheck disable=SC1090
    if ! source "$venv/bin/activate"; then
        printf "ERROR: failed to activate vLLM environment: %s\n" "$venv" | tee -a "$preflight_log" >&2
        return 74
    fi
    if [ "${VIRTUAL_ENV:-}" != "$venv" ]; then
        printf "ERROR: activation selected unexpected VIRTUAL_ENV: %s\n" "${VIRTUAL_ENV:-unset}" | tee -a "$preflight_log" >&2
        return 74
    fi
    if [ "$(command -v python)" != "$venv/bin/python" ]; then
        printf "ERROR: activation selected unexpected Python: %s\n" "$(command -v python)" | tee -a "$preflight_log" >&2
        return 74
    fi
    printf "python=%s\n" "$(command -v python)" >> "$preflight_log"
    printf "preflight_bootstrap=PASS\n" >> "$preflight_log"
}
