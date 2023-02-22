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
    --domain thecloudsphere \
    --name thecloudsphere-client1
```

### Manage all projects in a domain

```
tox -- \
    --domain thecloudsphere
```

### Create a project with a user

```
tox -e create -- \
    --domain thecloudsphere \
    --name client1 \
    --create-user
+----------+------------------------+----------------------------------+
| name     | value                  | id                               |
|----------+------------------------+----------------------------------|
| domain   | thecloudsphere         | 523d11f781a34f2383885d9d8ee465e4 |
| project  | thecloudsphere-client1 | bd5ddc5c09d04784913a4808ec21e1d3 |
| user     | thecloudsphere-client1 | 31f5f736109b4a8596937fe9ef51e2a4 |
| password | LPExeNeCMeRfuD8i       |                                  |
+----------+------------------------+----------------------------------+
```

### Create a customised project

```
tox -e create -- \
    --quota-router=3 \
    --quota-multiplier=2 \
    --domain thecloudsphere \
    --owner client1@demo.thecloudsphere.io \
    --name client1 \
    --nodomain-name-prefix \
    --managed-network-resources
```
