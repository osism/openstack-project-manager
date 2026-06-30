# Integration test

This integration test exercises the real project-creation path of
`openstack-project-manager` against a **live Keystone** instead of mocks.
Keystone is deployed locally on a [kind](https://kind.sigs.k8s.io/) cluster via
[forge](https://github.com/c5c3/forge) (its ControlPlane Quick Start), and the
test then creates one project using the admin account and verifies it through
the OpenStack SDK.

It is deliberately a scaffold: one happy-path test. The unit suite under
`test/unit/` keeps everything mocked; this harness is the first thing that
talks to a real `openstack.connect()` / `keystone.projects.update()` path.

## Prerequisites

- A Docker-capable host with the Docker daemon running.
- Outbound network access (to clone forge, pull operator images, and resolve
  `keystone.127-0-0-1.nip.io` via [nip.io](https://nip.io/) to `127.0.0.1`).
- For local runs, `openstacksdk` and `tox` must be importable in the active
  environment (the CI job installs them into a throwaway venv). `kind` and
  `kubectl` are installed by forge's own `make install-test-deps` into
  `~/.local/bin`; the scripts prepend that directory to `PATH`.

## Usage

```bash
# Full cycle: provision kind + Keystone, create a project, verify it, and tear
# the cluster down on every exit path (including failure).
make integration

# Deploy Keystone and leave the cluster running for local debugging.
make integration-up

# Tear down the cluster left running by `make integration-up`.
make integration-down
```

`make integration` only deletes a cluster it created itself. If a kind cluster
named `forge` already exists (for example one you started with
`make integration-up`), it is reused and left in place on exit.

## Environment overrides

| Variable | Default | Purpose |
|---|---|---|
| `FORGE_REF` | pinned commit | forge git ref to check out (pinned for reproducibility). |
| `FORGE_DIR` | `${TMPDIR:-/tmp}/opm-forge` | Where forge is cloned. |
| `CLUSTER_NAME` | `forge` | kind cluster name. |
| `KIND_HOST_PORT` | `8443` | Host port the Envoy Gateway (and Keystone) is exposed on. |
| `NAMESPACE` | `openstack` | Namespace the ControlPlane CR is applied to. |
| `OS_CLIENT_CONFIG_FILE` | `test/integration/clouds.yaml` | Generated clouds.yaml path. |
| `KEEP_PROJECT` | `0` | Set to `1` to keep the created project after `verify.py` (the cluster is torn down regardless). |

## What is asserted

After `tox -e create` creates the project as admin, `verify.py` connects with
the OpenStack SDK and asserts that:

- the `default` domain resolves,
- the `opm-integration-test` project exists in it, and
- the per-project group of the same name exists.

`verify.py` exits non-zero on any failed assertion. It is a standalone script,
not a `unittest`/`pytest` test, and is not named `test_*.py`, so the fast unit
gate (`tox -e test`) never collects it.

## Credentials

No real credentials are committed. `deploy_keystone.sh` reads the admin
password from the operator-projected
`controlplane-keystone-admin-credentials` Secret and writes an ephemeral
`clouds.yaml` (gitignored) with `verify: false`, because the Envoy Gateway
serves a self-signed cert. `run.sh` removes the generated `clouds.yaml` on
exit.
