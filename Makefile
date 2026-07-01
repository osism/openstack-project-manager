CLUSTER_NAME ?= forge
export CLUSTER_NAME

.PHONY: integration integration-up integration-down

# Full cycle: provision kind + Keystone, create a project, verify it, then
# tear the cluster down (always, including on failure).
integration:
	test/integration/run.sh

# Deploy Keystone and leave the cluster running for local debugging.
integration-up:
	test/integration/deploy_keystone.sh

# Tear down the cluster created by integration-up.
integration-down:
	kind delete cluster --name $(CLUSTER_NAME)
