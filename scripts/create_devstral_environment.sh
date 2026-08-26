#!/usr/bin/env bash
# Create only the isolated Devstral runtime; never mutate the primary environment.
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bootstrap_python="${DEVSTRAL_BOOTSTRAP_PYTHON:-python3.11}"
environment_directory="${DEVSTRAL_ENV_DIR:-$repository_root/.runtime/devstral-small-2507}"
requirements="$repository_root/environments/devstral-small-2507/requirements-cu128.txt"

if [[ -e "$environment_directory" ]]; then
  printf 'Refusing to overwrite existing Devstral environment: %s\n' "$environment_directory" >&2
  exit 2
fi
if ! command -v "$bootstrap_python" >/dev/null 2>&1; then
  printf 'Devstral bootstrap interpreter is unavailable: %s\n' "$bootstrap_python" >&2
  exit 2
fi
python_version="$($bootstrap_python -c 'import platform; print(platform.python_version())')"
if [[ "$python_version" != "3.11.11" ]]; then
  printf 'Python 3.11.11 is required for the Devstral environment; found %s.\n' "$python_version" >&2
  exit 2
fi

"$bootstrap_python" -m venv "$environment_directory"
"$environment_directory/bin/python" -m pip install --upgrade pip==25.1.1
"$environment_directory/bin/python" -m pip install -r "$requirements"
"$environment_directory/bin/python" -m pip install --no-deps --editable "$repository_root"
"$environment_directory/bin/python" -m pip check
"$environment_directory/bin/python" -m pip freeze --all > "$environment_directory/environment-freeze.txt"

printf 'Created isolated Devstral environment: %s\n' "$environment_directory"
printf 'Activate with: source %q\n' "$environment_directory/bin/activate"
