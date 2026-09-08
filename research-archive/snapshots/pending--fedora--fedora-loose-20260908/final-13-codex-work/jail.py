#!/usr/bin/env python3
"""Create a minimal filesystem inside a caller-created user/mount/PID namespace."""
import argparse
import ctypes
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--workspace', required=True)
p.add_argument('--runtime', required=True)
p.add_argument('--release', required=True)
p.add_argument('command', nargs=argparse.REMAINDER)
a = p.parse_args()
root = Path(a.root)

def mount(*args):
    subprocess.run(['/bin/mount', *map(str, args)], check=True, stdout=subprocess.DEVNULL)

mount('--make-rprivate', '/')
mount('-t', 'tmpfs', '-o', 'size=256m', 'tmpfs', root)

def bind(source, target, readonly=False):
    source = Path(source)
    target = root / target.lstrip('/')
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    mount('--bind', source, target)
    if readonly:
        mount('-o', 'remount,bind,ro', target)

for path in ('/usr', '/bin', '/sbin', '/lib', '/lib64', '/etc'):
    if Path(path).exists():
        bind(path, path, True)
if Path('/run/systemd/resolve').exists():
    bind('/run/systemd/resolve', '/run/systemd/resolve', True)
for name in ('null', 'zero', 'full', 'random', 'urandom', 'tty'):
    bind('/dev/' + name, '/dev/' + name)
for path in ('proc', 'tmp', 'home/pilot', 'dev/shm', 'dev/pts', '.oldroot'):
    (root / path).mkdir(parents=True, exist_ok=True)
os.chmod(root / 'tmp', 0o1777)
mount('-t', 'proc', 'proc', root / 'proc')
mount('-t', 'devpts', '-o', 'newinstance,ptmxmode=0666', 'devpts', root / 'dev/pts')
(root / 'dev/ptmx').symlink_to('pts/ptmx')
(root / 'dev/fd').symlink_to('/proc/self/fd')
bind(a.workspace, '/workspace')
bind(a.runtime, '/runtime')
bind(a.release, '/opt/codex', True)
# pivot_root, unlike chroot, permits Codex to create its nested command sandbox.
libc = ctypes.CDLL(None, use_errno=True)
os.chdir(root)
if libc.syscall(155, os.fsencode(root), os.fsencode(root / '.oldroot')) != 0:
    raise OSError(ctypes.get_errno(), 'pivot_root failed')
os.chdir('/workspace')
if libc.umount2(b'/.oldroot', 2) != 0:
    raise OSError(ctypes.get_errno(), 'old root detach failed')
os.rmdir('/.oldroot')
env = {'PATH': '/usr/bin:/bin:/opt/codex/bin', 'HOME': '/home/pilot',
       'CODEX_HOME': '/runtime/codex', 'TMPDIR': '/tmp', 'LANG': 'C.UTF-8',
       'PYTHONPATH': '/workspace', 'PYTHONDONTWRITEBYTECODE': '1',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
command = a.command[1:] if a.command and a.command[0] == '--' else a.command
os.execvpe(command[0], command, env)
