ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim 

COPY . /openstack-project-manager
COPY scripts/entrypoint.sh /entrypoint.sh

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN <<EOF
set -e
set -x

# install requiered packages
apt-get update
apt-get install -y --no-install-recommends \
  build-essential \
  gcc \
  git \
  cron \
  libldap2-dev \
  libsasl2-dev

rm -f /etc/cron.d/*
rm -f /etc/cron.daily/*

# install openstack-project-manager
python3 -m pip --no-cache-dir install -r /openstack-project-manager/requirements.txt


# cleanup
apt-get clean
rm -rf \
  /src \
  /tmp/* \
  /usr/share/doc/* \
  /usr/share/man/* \
  /var/lib/apt/lists/* \
  /var/tmp/*

pip3 install --no-cache-dir pyclean==3.0.0
pyclean /usr
pip3 uninstall -y pyclean
EOF

WORKDIR /openstack-project-manager
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "src/manager.py"]
