#!/bin/sh
CLOUD=${CLOUD:-admin}
SCHEDULE=${SCHEDULE:-0 * * * *}

env >> /etc/environment
# build cronjob entry
croncmd="cd /openstack-project-manager; python3 src/manage.py --cloud $CLOUD "$@"  > /proc/1/fd/1 2>/proc/1/fd/2"

echo "SHELL=/bin/bash" >> /etc/cron.d/openstack-project-manager
echo "BASH_ENV=/etc/environment" >> /etc/cron.d/openstack-project-manager
echo "$SCHEDULE root $croncmd" >> /etc/cron.d/openstack-project-manager

cron -l 2 -f
