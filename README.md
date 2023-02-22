# openstack-project-manager

- [New project](#new-project)
- [Usage](#usage)

## New project

```
tox -e create -- \
    --has-public-network \
    --name testing \
    --domain testing
```

## Usage

The cloud environment to be used can be specified via the ``--cloud``
parameter. ``service`` is set as the default.

The path to the definitions of the quota classes is set via the
parameter ``--classes``. ``etc/classes.yml`` is set as the default.

The dry drun mode can be activated via ``--dry-run``.

### Manage a single project

```
tox -- \
    --domain DOMAIN \
    --name PROJECT
```

### Manage all projects in a domain

```
tox -- \
    --domain DOMAIN
```

### Create a customised project

```
tox -e create -- \
    --quota-router=3 \
    --quota-multiplier=2 \
    --domain betacloud \
    --owner foo@osism.tech \
    --name foo \
    --nodomain-name-prefix \
    --managed-network-resources
```

### Create an Okeanos project

```
tox -e create -- \
    --domain okeanos \
    --owner okeanos@osism.tech
    --create-user \
    --quota-class okeanos \
    --name test
```
