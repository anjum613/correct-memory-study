#!/bin/bash
# Execute one command in a pinned SusVibes rootfs without Docker or setuid Singularity.
set -euo pipefail

die() {
  echo "susvibes-rootfs-exec: $*" >&2
  exit 2
}

if [[ "${1:-}" == "--inside" ]]; then
  shift
  [[ $# -ge 3 ]] || die "internal invocation is incomplete"
  rootfs=$1
  repository=$2
  shift 2

  mount --make-rprivate /
  mount --bind "$rootfs" "$rootfs"
  mount -o remount,ro,bind "$rootfs"
  mount --bind "$repository" "$rootfs/project"
  mount -t tmpfs -o mode=1777,nodev,nosuid tmpfs "$rootfs/tmp"
  mount -t tmpfs -o mode=0700,nodev,nosuid tmpfs "$rootfs/root"
  mount -t tmpfs -o mode=0755,nodev,nosuid tmpfs "$rootfs/dev"
  mkdir -p "$rootfs/dev/shm"
  mount -t tmpfs -o mode=1777,nodev,nosuid tmpfs "$rootfs/dev/shm"
  for device in null zero random urandom; do
    touch "$rootfs/dev/$device"
    mount --bind "/dev/$device" "$rootfs/dev/$device"
  done
  mount -t proc -o nosuid,nodev,noexec proc "$rootfs/proc"
  /usr/sbin/ip link set lo up

  exec /usr/sbin/chroot "$rootfs" /usr/bin/env -i \
    HOME=/root \
    TMPDIR=/tmp \
    PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    /.singularity.d/actions/exec "$@"
fi

[[ $# -ge 3 ]] || die "usage: $0 ROOTFS REPOSITORY COMMAND [ARG ...]"
rootfs=$1
repository=$2
shift 2
[[ "$rootfs" == /* && "$repository" == /* ]] || die "rootfs and repository must be absolute"
[[ -d "$rootfs" && ! -L "$rootfs" ]] || die "rootfs must be a real directory"
[[ -d "$repository" && ! -L "$repository" ]] || die "repository must be a real directory"
rootfs=$(realpath -e "$rootfs")
repository=$(realpath -e "$repository")
[[ -x "$rootfs/.singularity.d/actions/exec" ]] || die "rootfs lacks Singularity environment entrypoint"
[[ -d "$rootfs/project" ]] || die "rootfs lacks /project mountpoint"

exec unshare \
  --user --map-root-user \
  --mount \
  --pid --fork \
  --net \
  --ipc \
  --uts \
  "$0" --inside "$rootfs" "$repository" "$@"
