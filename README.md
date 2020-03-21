# openstack-project-manager

[![Build Status](https://travis-ci.org/betacloud/openstack-project-manager.svg?branch=master)](https://travis-ci.org/betacloud/openstack-project-manager)

- [New project](#new-project)
- [Usage](#usage)

## New project

```
openstack --os-cloud service project create --domain testing testing
openstack --os-cloud service project set --domain testing --property quotaclass=basic testing
openstack --os-cloud service project set --domain testing --property quotamultiplier=1 testing
openstack --os-cloud service project set --domain testing --property has_domain_network=False testing
openstack --os-cloud service project set --domain testing --property has_public_network=False testing
openstack --os-cloud service project set --domain testing --property has_shared_router=True testing
```

## Usage

The cloud environment to be used can be specified via the ``--cloud``
parameter. ``service`` is set as the default.

The path to the definitions of the quota classes is set via the
parameter ``--classes``. ``etc/classes.yml`` is set as the default.

The dry drun mode can be activated via ``--dry-run``.

### Manage a single project

```
tox -- --domain DOMAIN --name PROJECT
```

### Manage all projects in a domain

```
tox -- --domain DOMAIN
```
