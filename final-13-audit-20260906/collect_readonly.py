"""Stream existing evidence to stdout; never write on the remote filesystem."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
from datetime import datetime, timezone

BASE = Path('/home/s224049759/projects/final-experiment-runs')
CODEX = (
    'controlled-synthetic-final-13-codex-v3',
    'controlled-synthetic-final-13-codex-terra-medium-v1',
)
NATIVE = (
    'controlled-synthetic-final-13-qwen3-coder-native-recommended-v1',
    'controlled-synthetic-final-13-qwen3-coder-next-native-recommended-v2',
    'controlled-synthetic-final-13-devstral-native-recommended-v2',
)
SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', 'plugins', 'cache', 'skills',
             'agent-home', 'agent-tmp', 'agent-bin', 'jail', 'jail-agent',
             'jail-command', 'jail-isolation', 'jail-feature', 'jail-focal', 'jail-existing'}
SKIP_NAMES = {'auth.json', 'runner.lock', 'watchdog.lock'}
paths = set()

def add(path):
    if path.is_file() and not path.is_symlink() and path.name not in SKIP_NAMES:
        paths.add(path)

def walk(root):
    if not root.exists(): return
    for directory, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not Path(directory, d).is_symlink()]
        for filename in files:
            if not filename.endswith(('.pyc', '.lock')):
                add(Path(directory, filename))

for name in CODEX:
    root = BASE / name
    for p in root.iterdir():
        if p.is_file(): add(p)
    for sub in ('frozen', 'reports', 'runtime-amendments', 'preflight'):
        walk(root / sub)
    for run in sorted((root / 'runs').iterdir()):
        for attempt in sorted((run / 'attempts').iterdir()):
            record = attempt / 'record'
            if record.exists():
                for p in record.iterdir():
                    if p.is_file(): add(p)
            for sub in ('record/native-codex-home/sessions', 'runtime/codex-home/sessions',
                        'workspace', 'evaluation'):
                walk(attempt / sub)
            add(record / 'native-codex-home/config.toml')
for name in NATIVE:
    root = BASE / name
    for p in root.iterdir():
        if p.is_file(): add(p)
    for result in sorted(root.glob('*/result.json')):
        walk(result.parent)

inventory = []
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as archive:
    for p in sorted(paths):
        before = p.stat()
        data = p.read_bytes()
        after = p.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('source changed during read: ' + str(p))
        relative = str(p.relative_to(BASE))
        info = tarfile.TarInfo(relative)
        info.size = len(data)
        info.mtime = before.st_mtime
        archive.addfile(info, io.BytesIO(data))
        inventory.append({'path': relative, 'remote_path': str(p), 'bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest(), 'mtime_ns': before.st_mtime_ns})
    manifest = {'captured_at_utc': datetime.now(timezone.utc).isoformat(),
                'remote_root': str(BASE), 'selected_roots': CODEX + NATIVE,
                'omitted': 'Credentials, installed plugin/cache binaries, virtual environments, .git, jails; full session JSONL retained.',
                'files': inventory}
    data = (json.dumps(manifest, indent=2) + '\n').encode()
    info = tarfile.TarInfo('__audit_source_manifest.json')
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))
print(json.dumps({'files': len(inventory), 'bytes': sum(x['bytes'] for x in inventory)}), file=sys.stderr)
