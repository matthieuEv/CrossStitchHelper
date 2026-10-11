#!/bin/sh
# Makes the data directory writable, then runs the application unprivileged.
#
# The image cannot know who owns the host directory bind-mounted on /data: on
# Linux it is root when Docker created it, the host user when they created it
# themselves, and a fixed application uid could write in neither. So the
# container starts as root, picks the uid to run as, hands it the data
# directory, and drops its privileges before starting the application.
#
# - PUID/PGID, when set, are used as-is.
# - Otherwise the owner of the data directory is reused when it is not root,
#   so that files written to ./data stay the host user's own (backups, `rm`).
# - Otherwise (directory created by Docker, owned by root) the image's `csh`
#   user is used.
#
# If the filesystem refuses the ownership change and leaves the directory
# unwritable (some Windows or NAS mounts), the application runs as root rather
# than not starting at all.
set -eu

data_dir="${CSH_DATA_DIR:-/data}"

# Started with `user:` / `--user`: whoever chose the uid owns the permissions.
if [ "$(id -u)" != 0 ]; then
    exec "$@"
fi

mkdir -p "$data_dir"

owner_uid="$(stat -c %u "$data_dir")"
owner_gid="$(stat -c %g "$data_dir")"
if [ "$owner_uid" != 0 ]; then
    default_uid="$owner_uid"
    default_gid="$owner_gid"
else
    default_uid="$(id -u csh)"
    default_gid="$(id -g csh)"
fi
uid="${PUID:-$default_uid}"
gid="${PGID:-$default_gid}"

# Only what is not already right is changed, so that a restart stays fast
# however much data has accumulated.
find "$data_dir" \( ! -user "$uid" -o ! -group "$gid" \) \
    -exec chown "$uid:$gid" {} + 2>/dev/null || true

if setpriv --reuid="$uid" --regid="$gid" --clear-groups test -w "$data_dir"; then
    exec setpriv --reuid="$uid" --regid="$gid" --clear-groups "$@"
fi

echo "WARNING: $data_dir is not writable by uid $uid and its ownership could not be changed; running as root instead." >&2
exec "$@"
