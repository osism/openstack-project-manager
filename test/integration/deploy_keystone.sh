#!/usr/bin/env bash
# Deploy a Keystone-only forge ControlPlane on a kind cluster and emit a
# clouds.yaml the project-manager can authenticate against.
#
# Safe to run standalone (see `make integration-up`). A kind cluster of the
# same name that already exists is reused; this script does not delete it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Track the latest forge main; forge is a fast-moving prototyping repo and we
# deliberately do not pin to a commit. main caps each kind node's containerd
# RLIMIT_NOFILE (default 1048576) inside deploy-infra before any workload is
# scheduled. Docker Desktop's containerd ships LimitNOFILE=infinity, so pods
# otherwise inherit an ~1e9 open-file limit and uWSGI (the Keystone API server)
# pre-allocates multiple GiB per worker and is OOM-killed within seconds of
# spawning; raising the memory limit does not help. The cap lets Keystone come
# up at its default 512Mi/2-worker footprint. main also carries the single-node
# backing-service defaults our controlplane.yaml relies on
# (infrastructure.{database,cache}.replicas).
FORGE_REF="${FORGE_REF:-main}"
FORGE_DIR="${FORGE_DIR:-${TMPDIR:-/tmp}/opm-forge}"

NAMESPACE="${NAMESPACE:-openstack}"
KIND_HOST_PORT="${KIND_HOST_PORT:-8443}"
CLOUDS_FILE="${OS_CLIENT_CONFIG_FILE:-${HERE}/clouds.yaml}"

# Refuse to clobber an existing file outside our dedicated in-tree path. An
# operator who exports OS_CLIENT_CONFIG_FILE to point at their real
# ~/.config/openstack/clouds.yaml would otherwise have it truncated and
# replaced with throwaway test admin credentials by the write in step 3.
if [[ -e "${CLOUDS_FILE}" && "${CLOUDS_FILE}" != "${HERE}/clouds.yaml" ]]; then
    echo "Refusing to overwrite existing ${CLOUDS_FILE}." >&2
    echo "Unset OS_CLIENT_CONFIG_FILE or point it at a throwaway path." >&2
    exit 1
fi

# 1. forge toolchain + infra -------------------------------------------------
# forge's own installer pins kind/kubectl into ${HOME}/.local/bin.
if [[ ! -d "${FORGE_DIR}/.git" ]]; then
    git clone https://github.com/c5c3/forge.git "${FORGE_DIR}"
fi
# Fetch and check out the tip of ${FORGE_REF} (default: main) as a detached
# HEAD, so a reused clone always advances to the latest commit instead of
# staying on a stale local branch.
git -C "${FORGE_DIR}" fetch --quiet origin "${FORGE_REF}"
git -C "${FORGE_DIR}" checkout --quiet FETCH_HEAD

make -C "${FORGE_DIR}" install-test-deps
export PATH="${HOME}/.local/bin:${PATH}"

# Pin the optional forge stacks off: this Keystone-only integration test needs
# neither Chaos Mesh nor the Prometheus stack, and they only add provisioning
# time and load. These are forge's defaults today; set them explicitly so a
# future forge default flip cannot silently pull them in. The Garage object
# store (S3 backend for forge's Glance suites) has no such flag: current forge
# main deploys it unconditionally and waits for the GarageCluster to reach
# Running, so deploy-infra now also brings up the garage-operator plus a
# single-replica Garage pod (the kind overlay patches the 3-replica production
# baseline down). Harmless for this test beyond the extra provisioning time.
KIND_HOST_PORT="${KIND_HOST_PORT}" WITH_CONTROLPLANE=true \
    WITH_CHAOS_MESH=false WITH_PROMETHEUS=false \
    make -C "${FORGE_DIR}" deploy-infra

# 2. Keystone-only ControlPlane ---------------------------------------------
kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 \
    || kubectl create namespace "${NAMESPACE}"
# The tracked CR carries the harness default port 8443. Inject the effective
# KIND_HOST_PORT into spec.services.keystone.publicEndpoint so Keystone
# advertises the actually reachable URL in its catalog when the port is
# overridden (e.g. a second cluster beside a dev cluster already holding
# 8443) -- the same discipline forge's deploy-infra applies to its bundled CR.
# yq (mikefarah) is guaranteed here: deploy-infra hard-requires it on the
# WITH_CONTROLPLANE path and its pre-flight ran before this step.
cp_manifest="$(mktemp)"
KIND_HOST_PORT="${KIND_HOST_PORT}" yq eval \
    '.spec.services.keystone.publicEndpoint = "https://keystone.127-0-0-1.nip.io:" + strenv(KIND_HOST_PORT) + "/v3"' \
    "${HERE}/controlplane.yaml" > "${cp_manifest}"
kubectl apply -f "${cp_manifest}"
rm -f "${cp_manifest}"

# 3. OpenBao database-engine tenant onboarding -------------------------------
# forge defaults a managed-mode ControlPlane to Dynamic (engine-issued) DB
# credentials; the static per-ControlPlane credential seed was retired. The
# engine-issued creds path database/mariadb/creds/keystone-<namespace> only
# exists once setup-database-tenant.sh has provisioned the per-tenant
# connection and role, and deploy-infra runs that hook only when it applies the
# bundled CR itself (WITH_CONTROLPLANE_CR=true). This harness applies its own
# CR, so mirror deploy-infra's openbao_onboard_database_tenant here: wait for
# the projected MariaDB to be Ready, then run the (idempotent) tenant script
# with the OpenBao root token. Without this, DBCredentialsReady never turns
# True and the Ready wait below times out.
echo "Waiting for MariaDB openstack-db to be projected..."
for _ in $(seq 1 30); do
    if kubectl get mariadb/openstack-db -n "${NAMESPACE}" >/dev/null 2>&1; then
        break
    fi
    sleep 10
done
kubectl wait mariadb/openstack-db -n "${NAMESPACE}" \
    --for=condition=Ready --timeout=600s

BAO_TOKEN="$(kubectl get secret openbao-init-keys -n openbao-system \
    -o jsonpath='{.data.init-output}' | base64 -d | jq -r '.root_token')"
if [[ -z "${BAO_TOKEN}" || "${BAO_TOKEN}" == "null" ]]; then
    echo "ERROR: could not extract the OpenBao root token from" \
        "openbao-system/openbao-init-keys." >&2
    exit 1
fi
export BAO_TOKEN
bash "${FORGE_DIR}/deploy/openbao/bootstrap/setup-database-tenant.sh" \
    "${NAMESPACE}" controlplane
unset BAO_TOKEN

# Wait for the ControlPlane's aggregate Ready condition. A bare
# `kubectl wait --for=condition=Ready --timeout=15m` is silent for the whole
# window, so a stuck sub-condition (the operator reconciles them in order:
# NamespacesReady -> InfrastructureReady -> ESOTenantStoreReady ->
# DBCredentialsReady -> KeystoneReady -> KORCReady -> AdminCredentialReady ->
# CatalogReady -> ServiceAccountsReady; HorizonReady joins after KeystoneReady
# only when services.horizon is set) is indistinguishable from a dead hang in
# the CI log. Poll
# instead and print the first not-yet-True condition each tick, so the log
# shows which stage is pending; on timeout dump the full CR before failing
# (the verbose pod/event dump is left to run.sh's diagnostics trap).
cp_timeout="${CONTROLPLANE_TIMEOUT:-900}"
cp_deadline=$(($(date +%s) + cp_timeout))
while true; do
    if [[ "$(kubectl get controlplane/controlplane -n "${NAMESPACE}" \
        -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' \
        2>/dev/null)" == "True" ]]; then
        echo "ControlPlane/controlplane is Ready."
        break
    fi
    pending="$(kubectl get controlplane/controlplane -n "${NAMESPACE}" -o json 2>/dev/null \
        | jq -r 'first(.status.conditions[]? | select(.type != "Ready" and .status != "True")
                 | "\(.type)=\(.status) (\(.reason)): \(.message)") // "status not reported yet"')"
    echo "  ControlPlane/controlplane not Ready yet: ${pending}"
    if [[ "$(date +%s)" -ge "${cp_deadline}" ]]; then
        echo "ERROR: ControlPlane/controlplane not Ready after ${cp_timeout}s." >&2
        kubectl get controlplane/controlplane -n "${NAMESPACE}" -o yaml || true
        exit 1
    fi
    sleep 15
done

# 4. clouds.yaml from the operator-projected admin credentials --------------
admin_password="$(kubectl get secret controlplane-keystone-admin-credentials \
    -n "${NAMESPACE}" -o jsonpath='{.data.password}' | base64 -d)"

# Serialize with a YAML library rather than a heredoc: the minted admin
# password is arbitrary bytes, and a `"` or `\` interpolated into a quoted YAML
# scalar would corrupt the file or silently change the value via escape
# processing.
umask 077
ADMIN_PASSWORD="${admin_password}" KIND_HOST_PORT="${KIND_HOST_PORT}" \
    CLOUDS_FILE="${CLOUDS_FILE}" python3 - <<'PY'
import os

import yaml

data = {
    "clouds": {
        "admin": {
            "auth": {
                "auth_url": f"https://keystone.127-0-0-1.nip.io:{os.environ['KIND_HOST_PORT']}/v3",
                "username": "admin",
                "password": os.environ["ADMIN_PASSWORD"],
                "project_name": "admin",
                "user_domain_name": "Default",
                "project_domain_name": "Default",
            },
            "identity_api_version": 3,
            "verify": False,
        }
    }
}
with open(os.environ["CLOUDS_FILE"], "w") as f:
    yaml.safe_dump(data, f, default_flow_style=False)
PY
echo "Wrote clouds.yaml to ${CLOUDS_FILE}"

# 5. Ensure the roles create.py expects exist on the bare Keystone ----------
# create.py indexes its role cache directly (CACHE_ROLES[role_name]) when it
# assigns DEFAULT_ROLES = member, load-balancer_member, so a missing role
# aborts the run. A bare forge Keystone ships member but not
# load-balancer_member (Octavia provisions that one), so pre-create it here.
# Idempotent.
export OS_CLIENT_CONFIG_FILE="${CLOUDS_FILE}"
python3 - <<'PY'
import openstack

cloud = openstack.connect(cloud="admin")
for name in ("member", "load-balancer_member"):
    if cloud.identity.find_role(name) is None:
        cloud.identity.create_role(name=name)
        print(f"Created role: {name}")
    else:
        print(f"Role already present: {name}")
PY
