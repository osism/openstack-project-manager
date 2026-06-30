# SPDX-License-Identifier: AGPL-3.0-or-later

"""Standalone OpenStack SDK assertions for the integration test.

This script is intentionally NOT a unittest/pytest test and is deliberately
not named ``test_*.py`` so that ``tox -e test``
(``python -m unittest discover ./test``) never collects it. It is invoked
directly by ``run.sh`` after the project has been created and exits non-zero
on any failed assertion.
"""

import sys

import openstack

PROJECT_NAME = "opm-integration-test"
DOMAIN_NAME = "default"


def main() -> int:
    """Assert the integration project and its group exist via the SDK."""
    cloud = openstack.connect(cloud="admin")

    domain = cloud.identity.find_domain(DOMAIN_NAME)
    assert domain is not None, f"domain {DOMAIN_NAME!r} not found"

    project = cloud.identity.find_project(PROJECT_NAME, domain_id=domain.id)
    assert project is not None, f"project {PROJECT_NAME!r} not found"

    group = cloud.identity.find_group(PROJECT_NAME, domain_id=domain.id)
    assert group is not None, f"group {PROJECT_NAME!r} not found"

    print(f"OK: project {PROJECT_NAME!r} and group exist in domain {DOMAIN_NAME!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
