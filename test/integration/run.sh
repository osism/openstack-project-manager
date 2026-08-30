#!/usr/bin/env bash
# Orchestrate the Keystone integration test: deploy Keystone on kind via forge,
# create one project as admin through the real `tox -e create` path, and assert
# it via the OpenStack SDK.
#
# The kind cluster is always torn down on exit (success or failure), but only
# when this run actually created it -- a pre-existing debug cluster of the same
# name is reused and left in place. On failure a diagnostics dump is emitted
# before teardown.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"

CLUSTER_NAME="${CLUSTER_NAME:-forge}"
NAMESPACE="${NAMESPACE:-openstack}"
PROJECT_NAME="${PROJECT_NAME:-opm-integration-test}"

export PATH="${HOME}/.local/bin:${PATH}"
export OS_CLIENT_CONFIG_FILE="${HERE}/clouds.yaml"

# Record cluster ownership before we deploy so teardown only removes a cluster
# this run created.
CREATED_CLUSTER=0
if ! kind get clusters 2>/dev/null | grep -Fqx "${CLUSTER_NAME}"; then
    CREATED_CLUSTER=1
fi

dump_diagnostics() {
    echo "=== Diagnostics for kind cluster ${CLUSTER_NAME} ==="
    kubectl get nodes -o wide || true
    kubectl get pods -A -o wide || true
    kubectl get controlplane -n "${NAMESPACE}" -o yaml || true
    kubectl get events -A --sort-by=.lastTimestamp || true

    # Describe and dump logs for every Pod in the namespace, current AND
    # previous instance. A CrashLoopBackOff Pod (e.g. the projected
    # controlplane-keystone) keeps the failure only in its *previous* container
    # log, and `describe` carries the Last State (OOMKilled, exit code). We
    # iterate every Pod instead of a label selector on purpose: the c5c3-
    # projected Keystone Pods do not carry a stable app label we can rely on, so
    # an `-l application=keystone` selector silently matched nothing.
    echo "=== Pod descriptions and logs in namespace ${NAMESPACE} ==="
    for pod in $(kubectl get pods -n "${NAMESPACE}" \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
        echo "--- describe pod/${pod} ---"
        kubectl describe pod/"${pod}" -n "${NAMESPACE}" || true
        echo "--- logs pod/${pod} (current) ---"
        kubectl logs pod/"${pod}" -n "${NAMESPACE}" \
            --all-containers --tail=200 || true
        echo "--- logs pod/${pod} (previous) ---"
        kubectl logs pod/"${pod}" -n "${NAMESPACE}" \
            --all-containers --previous --tail=200 || true
    done
}

cleanup() {
    rc=$?
    if [[ "${rc}" -ne 0 ]]; then
        dump_diagnostics
    fi
    if [[ "${CREATED_CLUSTER}" -eq 1 ]]; then
        echo "Deleting kind cluster ${CLUSTER_NAME}"
        kind delete cluster --name "${CLUSTER_NAME}" || true
    else
        echo "Leaving pre-existing kind cluster ${CLUSTER_NAME} in place"
    fi
    rm -f "${OS_CLIENT_CONFIG_FILE}"
    exit "${rc}"
}
trap cleanup EXIT

"${HERE}/deploy_keystone.sh"

cd "${ROOT}"
tox -e create -- --cloud admin --domain default --name "${PROJECT_NAME}" \
    --nodomain-name-prefix --quota-class basic --nocreate-user

python "${HERE}/verify.py"

# Keep reruns idempotent by removing the project unless asked to keep it. The
# EXIT trap destroys the whole cluster anyway, so this is best-effort cleanup.
if [[ "${KEEP_PROJECT:-0}" != "1" ]]; then
    python3 - "${PROJECT_NAME}" <<'PY' || true
import sys

import openstack

name = sys.argv[1]
cloud = openstack.connect(cloud="admin")
domain = cloud.identity.find_domain("default")
project = cloud.identity.find_project(name, domain_id=domain.id)
if project is not None:
    cloud.identity.delete_project(project.id)
    print(f"Deleted project: {name}")
PY
fi
