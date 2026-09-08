#!/bin/bash
# Run an agent command in the prospectively qualified V2 filesystem boundary.
set -euo pipefail

die() {
  echo "v2-agent-sandbox: $*" >&2
  exit 2
}

if [[ "${1:-}" == "--inside" ]]; then
  shift
  [[ $# -ge 3 ]] || die "internal invocation is incomplete"
  sandbox_root=$1
  candidate=$2
  shift 2

  mount --make-rprivate /
  mount -t tmpfs -o mode=0755,nodev,nosuid tmpfs "$sandbox_root"
  mkdir -p \
    "$sandbox_root/usr" \
    "$sandbox_root/opt/miniconda3" \
    "$sandbox_root/workspace" \
    "$sandbox_root/tmp" \
    "$sandbox_root/home/agent" \
    "$sandbox_root/proc" \
    "$sandbox_root/dev" \
    "$sandbox_root/etc"

  mount --rbind /usr "$sandbox_root/usr"
  mount -o remount,ro,bind "$sandbox_root/usr"
  if [[ -d /opt/miniconda3 ]]; then
    mount --rbind /opt/miniconda3 "$sandbox_root/opt/miniconda3"
    mount -o remount,ro,bind "$sandbox_root/opt/miniconda3"
  fi
  mount --bind "$candidate" "$sandbox_root/workspace"
  mount -t tmpfs -o mode=1777,nodev,nosuid tmpfs "$sandbox_root/tmp"
  mount -t tmpfs -o mode=0755,nodev,nosuid tmpfs "$sandbox_root/dev"

  for device in null zero random urandom; do
    touch "$sandbox_root/dev/$device"
    mount --bind "/dev/$device" "$sandbox_root/dev/$device"
  done
  mount -t proc -o nosuid,nodev,noexec proc "$sandbox_root/proc"

  for etc_file in ld.so.cache nsswitch.conf hosts localtime; do
    if [[ -f "/etc/$etc_file" ]]; then
      touch "$sandbox_root/etc/$etc_file"
      mount --bind "/etc/$etc_file" "$sandbox_root/etc/$etc_file"
      mount -o remount,ro,bind "$sandbox_root/etc/$etc_file"
    fi
  done
  if [[ -d /etc/ssl/certs ]]; then
    mkdir -p "$sandbox_root/etc/ssl/certs"
    mount --rbind /etc/ssl/certs "$sandbox_root/etc/ssl/certs"
    mount -o remount,ro,bind "$sandbox_root/etc/ssl/certs"
  fi

  ln -s usr/bin "$sandbox_root/bin"
  ln -s usr/lib "$sandbox_root/lib"
  ln -s usr/lib64 "$sandbox_root/lib64"
  /usr/sbin/ip link set lo up

  exec /usr/sbin/chroot "$sandbox_root" /usr/bin/env -i \
    HOME=/home/agent \
    TMPDIR=/tmp \
    PATH=/opt/miniconda3/bin:/usr/bin:/bin \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    "$@"
fi

[[ $# -ge 2 ]] || die "usage: $0 CANDIDATE COMMAND [ARG ...]"
candidate=$1
shift
[[ "$candidate" == /* ]] || die "candidate must be an absolute path"
[[ -d "$candidate" && ! -L "$candidate" ]] || die "candidate must be a real directory"
candidate=$(realpath -e "$candidate")

runtime_parent=${CMPILOT_V2_SANDBOX_TMP_PARENT:-${TMPDIR:-/tmp}}
[[ -d "$runtime_parent" && ! -L "$runtime_parent" ]] || die "invalid runtime parent"
sandbox_root=$(mktemp -d "$runtime_parent/cmpilot-v2-sandbox.XXXXXX")
cleanup() {
  rmdir "$sandbox_root" 2>/dev/null || true
}
trap cleanup EXIT

unshare \
  --user --map-root-user \
  --mount \
  --pid --fork \
  --net \
  --ipc \
  --uts \
  "$0" --inside "$sandbox_root" "$candidate" "$@"
