# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file was started on Juli 05, 2024. Changes prior to this date are not included in the CHANGELOG.

## [v0.20261007.0] - 2026-10-07

### Changed
- Run all Zuul CI jobs on the ubuntu-noble nodeset (osism/openstack-project-manager#306)

### Fixed
- Fix mypy errors caused by updated type annotations in openstacksdk 4.20.0 (osism/openstack-project-manager#299)

### Dependencies
- click 8.4.2 → 8.5.0 (osism/openstack-project-manager#303)
- dynaconf 3.3.2 → 3.3.5 (osism/openstack-project-manager#298, osism/openstack-project-manager#300)
- openstacksdk 4.17.0 → 4.20.0 (osism/openstack-project-manager#299)
- python-ldap 3.4.7 → 3.4.8 (osism/openstack-project-manager#305)
- python-neutronclient 13.0.0 → 14.0.0 (osism/openstack-project-manager#304)
- typer 0.27.0 → 0.27.2 (osism/openstack-project-manager#301)

## [v0.20260722.0] - 2026-07-22

### Added
- Allow management of a project's default volume type via `--default-volume-type` and `--manage-defaultvolumetype/--nomanage-defaultvolumetype` options (osism/openstack-project-manager#262)
- Add workflow to automatically add opened issues and pull requests to project board (osism/openstack-project-manager#281)

### Changed
- Reformat code to comply with black 26.3.1 stable style (osism/openstack-project-manager#275)
- Allow specification of multiple classes.yml files, merging them with later files taking precedence (osism/openstack-project-manager#278)
- Fix project-board automation for fork PRs by switching to `pull_request_target` and scoping the handed-over secret to `ADD_TO_PROJECT_PAT` instead of inheriting all secrets (osism/openstack-project-manager#289)

### Fixed
- Remove parent key from quotaclass after merge so it no longer leaks into the result (osism/openstack-project-manager#280)
- Fix mypy errors with openstacksdk 4.17.0 by narrowing service proxies to the API versions this project uses (osism/openstack-project-manager#274)
- Handle find_domain and find_project returning None instead of failing later with an AttributeError (osism/openstack-project-manager#274)

### Removed
- Drop gate pipeline from Zuul configuration (osism/openstack-project-manager#292)

### Dependencies
- click 8.3.1 → 8.4.2 (osism/openstack-project-manager#273, osism/openstack-project-manager#276)
- deepmerge 2.0 → 2.1.0 (osism/openstack-project-manager#288)
- dynaconf 3.2.12 → 3.3.2 (osism/openstack-project-manager#271, osism/openstack-project-manager#290, osism/openstack-project-manager#291, osism/openstack-project-manager#295)
- openstacksdk 4.8.0 → 4.17.0 (osism/openstack-project-manager#261, osism/openstack-project-manager#266, osism/openstack-project-manager#274)
- python-ldap 3.4.5 → 3.4.7 (osism/openstack-project-manager#283)
- python-neutronclient 11.6.0 → 13.0.0 (osism/openstack-project-manager#259, osism/openstack-project-manager#268, osism/openstack-project-manager#282, osism/openstack-project-manager#296)
- tabulate 0.9.0 → 0.10.0 (osism/openstack-project-manager#269)
- typer 0.20.0 → 0.27.0 (osism/openstack-project-manager#258, osism/openstack-project-manager#263, osism/openstack-project-manager#264, osism/openstack-project-manager#265, osism/openstack-project-manager#267, osism/openstack-project-manager#277, osism/openstack-project-manager#284, osism/openstack-project-manager#285, osism/openstack-project-manager#286, osism/openstack-project-manager#287, osism/openstack-project-manager#297)

## [v0.20251128.0] - 2025-11-28

### Added
- Add volume quota limits to the service quota class (osism/openstack-project-manager#257)

### Changed
- Change volume type assignment errors to warnings, since missing or non-unique volume types are expected conditions rather than critical errors (osism/openstack-project-manager#255)

### Dependencies
- click 8.1.8 → 8.3.1 (osism/openstack-project-manager#227)

## [v0.20251115.0] - 2025-11-15

### Added
- Support creation of application credentials for users (osism/openstack-project-manager#248)
- Add a group for each project and domain, including a domain admin group with default role assignments (osism/openstack-project-manager#249)

### Fixed
- Fix SSL verification for application credentials by propagating verify and cacert settings to the user connection (osism/openstack-project-manager#252)
- Fix UnboundLocalError when creating domain with admin user (osism/openstack-project-manager#254)

### Dependencies
- typer 0.19.2 → 0.20.0 (osism/openstack-project-manager#250)
- openstacksdk 4.7.1 → 4.8.0 (osism/openstack-project-manager#253)

## [v0.20251012.0] - 2025-10-12

### Changed
- Skip projects without a quotaclass instead of applying a default quotaclass (osism/openstack-project-manager#247)

### Fixed
- Pin click to 8.1.8 to fix typer compatibility issues with click 8.2.0 (osism/openstack-project-manager#226)

### Dependencies
- openstacksdk 4.4.0 → 4.5.0 (osism/openstack-project-manager#223)
- typer 0.15.2 → 0.15.3 (osism/openstack-project-manager#224)
- dynaconf 3.2.10 → 3.2.11 (osism/openstack-project-manager#225)
- typer 0.15.3 → 0.15.4 (osism/openstack-project-manager#228)
- python-neutronclient 11.4.0 → 11.5.0 (osism/openstack-project-manager#230)
- openstacksdk 4.5.0 → 4.6.0 (osism/openstack-project-manager#233)
- typer 0.15.4 → 0.16.0 (osism/openstack-project-manager#232)
- python-neutronclient 11.5.0 → 11.6.0 (osism/openstack-project-manager#234)
- os-client-config 2.1.0 → 2.3.0 (osism/openstack-project-manager#235)
- typer 0.16.0 → 0.16.1 (osism/openstack-project-manager#238)
- openstacksdk 4.6.0 → 4.7.0 (osism/openstack-project-manager#237)
- typer 0.16.1 → 0.17.4 (osism/openstack-project-manager#239)
- openstacksdk 4.7.0 → 4.7.1 (osism/openstack-project-manager#240)
- typer 0.17.4 → 0.19.2 (osism/openstack-project-manager#241)
- pyyaml 6.0.2 → 6.0.3 (osism/openstack-project-manager#242)
- python-ldap 3.4.4 → 3.4.5 (osism/openstack-project-manager#245)
- dynaconf 3.2.11 → 3.2.12 (osism/openstack-project-manager#243)

## [v0.20250407.0] - 2025-04-07

### Added
- Automatically add named, private, admin-volume types to projects (osism/openstack-project-manager#189)
- Automatically add named, private, admin-flavors to projects (osism/openstack-project-manager#195)
- Support project groups in the manage_ldap script (osism/openstack-project-manager#200)
- Add network bandwidth limit policy check and management for projects using QoS policies (osism/openstack-project-manager#197)

### Changed
- Allow up to 1000 GByte volume storage for Okeanos projects (osism/openstack-project-manager#191)
- Rename the domain-manager role to manager (osism/openstack-project-manager#219)
- Improve and clean up logging output for quota classes, private volume types/flavors, and unmanaged projects (osism/openstack-project-manager#220, osism/openstack-project-manager#221)

### Fixed
- Fix handling of private flavors (osism/openstack-project-manager#202)
- Handle openstack.exceptions.HttpException when creating volumes during image caching (osism/openstack-project-manager#218)
- Fix flake8 formatting failure (osism/openstack-project-manager#210)
- Add missing `=` to quotaclass logging output (osism/openstack-project-manager#222)

### Dependencies
- openstacksdk 3.2.0 → 3.3.0 (osism/openstack-project-manager#186)
- dynaconf 3.2.5 → 3.2.6 (osism/openstack-project-manager#187)
- pyyaml 6.0.1 → 6.0.2 (osism/openstack-project-manager#190)
- typer 0.12.3 → 0.12.4 (osism/openstack-project-manager#192)
- typer 0.12.4 → 0.12.5 (osism/openstack-project-manager#193)
- deepmerge 1.1.1 → 2.0 (osism/openstack-project-manager#194)
- openstacksdk 3.3.0 → 4.0.0 (osism/openstack-project-manager#196)
- openstacksdk 4.0.0 → 4.1.0 (osism/openstack-project-manager#199)
- typer 0.12.5 → 0.13.0 (osism/openstack-project-manager#201)
- typer 0.13.0 → 0.13.1 (osism/openstack-project-manager#203)
- typer 0.13.1 → 0.14.0 (osism/openstack-project-manager#204)
- typer 0.14.0 → 0.15.1 (osism/openstack-project-manager#205)
- loguru 0.7.2 → 0.7.3 (osism/openstack-project-manager#206)
- openstacksdk 4.1.0 → 4.2.0 (osism/openstack-project-manager#209)
- python-neutronclient 11.3.1 → 11.4.0 (osism/openstack-project-manager#211)
- dynaconf 3.2.6 → 3.2.7 (osism/openstack-project-manager#212)
- openstacksdk 4.2.0 → 4.3.0 (osism/openstack-project-manager#213)
- dynaconf 3.2.7 → 3.2.9 (osism/openstack-project-manager#214)
- dynaconf 3.2.9 → 3.2.10 (osism/openstack-project-manager#215)
- openstacksdk 4.3.0 → 4.4.0 (osism/openstack-project-manager#216)
- typer 0.15.1 → 0.15.2 (osism/openstack-project-manager#217)

## [v0.20240705.0] - 2024-07-05

### Added
- Initial implementation of the OpenStack project manager for managing project quotas and network resources based on quota classes (osism/openstack-project-manager@29d3b52)
- Add automatic creation of per-project networking resources (router, network, subnet) for external network access, skipping service projects (osism/openstack-project-manager@df24b15, osism/openstack-project-manager@389196c, osism/openstack-project-manager@5d7295f, osism/openstack-project-manager@f8bc444, osism/openstack-project-manager@e81dd80, osism/openstack-project-manager@2e87ec9)
- Add support for shared router and service networks across projects in a domain (osism/openstack-project-manager@b20613f, osism/openstack-project-manager@56a051e, osism/openstack-project-manager@f864ffe, osism/openstack-project-manager@1dafc99, osism/openstack-project-manager@5e4e556)
- Add show_public_network option to expose the public network to a project without creating a router (osism/openstack-project-manager@f8d360e)
- Add configurable router quota per project (osism/openstack-project-manager@856f0f6, osism/openstack-project-manager@814eaa2, osism/openstack-project-manager@49e2f4d, osism/openstack-project-manager@1dc4546)
- README: document steps for creating a new project (osism/openstack-project-manager@7512c51)
- Add Apache License 2.0 LICENSE file and remove duplicate license text from README (osism/openstack-project-manager@9eae19f)
- Add availability zone hints when creating networks and routers (osism/openstack-project-manager@854cf6d)
- Add ability to remove external network RBAC policies when they are no longer needed (osism/openstack-project-manager@738738d)
- Add create.py script for creating test projects (osism/openstack-project-manager@b9ef59f)
- Add testbed quota class (osism/openstack-project-manager@3b897a3)
- Add support for assigning Keystone endpoint groups to projects (osism/openstack-project-manager@af96b94)
- Add has-domain-network, has-public-network and has-shared-router options to create.py (osism/openstack-project-manager@caf2eae)
- Add GitHub Actions workflows for YAML syntax checking and PR labeling, and Renovate configuration (osism/openstack-project-manager@bd25a63)
- Add create-endpoint-groups.py contrib script to manage Keystone endpoint groups (osism/openstack-project-manager@67070b7)
- Add temporary contrib helper scripts for creating users and adding them to projects (osism/openstack-project-manager@3333436)
- Allow projects with unmanaged network resources (osism/openstack-project-manager#2, osism/openstack-project-manager#3)
- Add swift endpoint to the default endpoint list (osism/openstack-project-manager#4)
- Add GitHub workflow to check Python syntax (osism/openstack-project-manager#5)
- Add create_external_network_rbacs method to manage RBAC policies for domain and public external networks (osism/openstack-project-manager#6)
- Add domain-name-prefix argument to the create script (osism/openstack-project-manager@77ec1cb)
- Add unmanaged-network-resources parameter to the create script (osism/openstack-project-manager#13)
- Add assign-admin-user parameter to automatically assign the domain admin user to new projects (osism/openstack-project-manager#17)
- Add README sample for creating a customised project (osism/openstack-project-manager@aaf391e)
- Add okeanos quota class (osism/openstack-project-manager@a1b3499, osism/openstack-project-manager@69b55e2)
- Add README sample for creating an Okeanos project (osism/openstack-project-manager@5e7eb56, osism/openstack-project-manager@eb50401)
- Add password-length and create-admin-user parameters to the create script, with improved random name and password generation (osism/openstack-project-manager#27)
- Add Pipfile and Pipfile.lock for dependency management (osism/openstack-project-manager@51c15ce)
- Add support for an internal ID for projects (osism/openstack-project-manager#55)
- Add skyline endpoint and tabulate dependency (osism/openstack-project-manager#56)
- Create non-existing domains automatically (osism/openstack-project-manager#60)
- Tag service projects (osism/openstack-project-manager#71)
- Support sharing images from a domain's images project with other projects in the same domain (osism/openstack-project-manager#81)
- Allow processing all domains and their projects when no name or domain is specified (osism/openstack-project-manager#76, osism/openstack-project-manager#77)
- Manage quota for the admin and service projects (osism/openstack-project-manager#85)
- Create the shared service network in the service project (osism/openstack-project-manager#87)
- Add a quota class definition for testbed deployments (osism/openstack-project-manager#92)
- Add periodic-daily zuul jobs for flake8 and yamllint (osism/openstack-project-manager#91)
- Support preparation of image cache for project images, including handling of minimum disk size and removal of stale cache volumes for deleted images (osism/openstack-project-manager#94, osism/openstack-project-manager#95, osism/openstack-project-manager#96)
- Add service_network_type property to configure the RBAC policy action for the service network (osism/openstack-project-manager#90)
- Add a script to create a new user (osism/openstack-project-manager#99)
- Support parent quotaclasses, allowing quota classes to inherit settings from a parent class (osism/openstack-project-manager#108)
- Support quota overwrites via project properties (osism/openstack-project-manager#110)
- Support permission management on home projects (osism/openstack-project-manager#111)
- Add script to sync home projects with a LDAP group (osism/openstack-project-manager#112)
- Add manage-ldap script to add all users in a certain LDAP group to all projects of a certain domain (osism/openstack-project-manager#134)
- Add mypy job to zuul CI pipeline (osism/openstack-project-manager#120)
- Assign the domain-manager role to the admin user when a new domain is created (osism/openstack-project-manager#142)
- Add --create-domain argument to create a domain without creating a project (osism/openstack-project-manager#146)
- Add --admin-domain argument to specify the user domain for the admin account (osism/openstack-project-manager#149)
- Add an unlimited quota class (osism/openstack-project-manager#150)
- Allow assigning the domain admin user to already created projects (osism/openstack-project-manager#154)
- Add support for volume types in quota classes (osism/openstack-project-manager#156)
- Add support for a public network in quota classes (osism/openstack-project-manager#157)
- Add unit tests for the create_user, manage_ldap, create_ldap, create, and project management modules (osism/openstack-project-manager#180)

### Changed
- Allow firewalls and firewall groups in the quota classes for service projects (osism/openstack-project-manager@a519dcb, osism/openstack-project-manager@2246a36, osism/openstack-project-manager@a4e82cf)
- Allow management of default security groups in the quota classes for service projects (osism/openstack-project-manager@25c189e, osism/openstack-project-manager@335d8fe)
- Respect custom public_network and domain_network project properties when naming network resources (osism/openstack-project-manager@f17ebb3)
- Refactor project boolean property checks into a check_bool helper and exclude service projects from router quota (osism/openstack-project-manager@b13da2a)
- Improve create.py quota and network options and rename CLI options to use dashes (osism/openstack-project-manager@49b4174, osism/openstack-project-manager@953dcb4)
- Make user creation in create.py configurable via the create-user option (osism/openstack-project-manager@1948549)
- Refactor default role assignment into a configurable list and assign the load-balancer_member role by default (osism/openstack-project-manager@cae103c, osism/openstack-project-manager@3d249f3)
- Update README to use the create.py script instead of manual CLI commands (osism/openstack-project-manager@c81ef7a)
- Increase testbed quota class limits for compute, network and volume resources (osism/openstack-project-manager@b810d45, osism/openstack-project-manager@6410417, osism/openstack-project-manager@c043133, osism/openstack-project-manager@5e0b0bb)
- Allow keypairs in the service quota class (osism/openstack-project-manager@05351e2)
- Add barbican, designate and octavia to the default endpoints (osism/openstack-project-manager@ec7b2ac)
- Pin requirements.txt dependencies to fixed versions (osism/openstack-project-manager@50229cb)
- Increase service quota class limits (osism/openstack-project-manager@f43e188)
- Do not create a new user by default in the create script (osism/openstack-project-manager@952e984)
- Add a public network by default in the create script (osism/openstack-project-manager@bc3e34b)
- Enable volume backups in the basic quota class (osism/openstack-project-manager#12)
- Use f-strings instead of % formatting in the create script (osism/openstack-project-manager#19, osism/openstack-project-manager#20)
- Run GitHub Actions branch builds on main branch only (osism/openstack-project-manager#28)
- Update Renovate configuration to use shared osism config presets (osism/openstack-project-manager@1c90e5d)
- Autoformat Python code with black (osism/openstack-project-manager@7da6ccc)
- Replace standard logging with loguru for log output (osism/openstack-project-manager@810610b)
- Use f-strings instead of %-style string formatting in manage.py (osism/openstack-project-manager@8c73588)
- Move create-endpoint-groups.py from contrib to src, use openstacksdk instead of shade, and default to the admin cloud (osism/openstack-project-manager@52fdd02, osism/openstack-project-manager@81807bb)
- Change default values for cloud, domain, quota class, owner and project name in create.py and manage.py (osism/openstack-project-manager@10adeb6, osism/openstack-project-manager@6d4411d, osism/openstack-project-manager@691371b, osism/openstack-project-manager@f8a1635, osism/openstack-project-manager@bb217ec)
- Refactor yaml syntax check to run via zuul instead of a dedicated github action (osism/openstack-project-manager#48)
- Add flake8 job to zuul (osism/openstack-project-manager#49)
- Use loguru for logging in create.py (osism/openstack-project-manager#50)
- Do not manage network resources by default (osism/openstack-project-manager#51)
- Do not assign an admin user by default (osism/openstack-project-manager#52)
- Change default public network to public (osism/openstack-project-manager#53)
- Assign creator role by default (osism/openstack-project-manager#54)
- Improve README documentation (osism/openstack-project-manager#58)
- Assign the basic quota class by default (osism/openstack-project-manager#61)
- Use tabulate instead of loguru for output in create.py (osism/openstack-project-manager#62)
- Update README samples (osism/openstack-project-manager#63)
- Use member role instead of _member_ (osism/openstack-project-manager@cc815f2)
- Use nova as the default network availability zone (osism/openstack-project-manager@c9c6674)
- Allow management of projects in the default domain except admin and service projects (osism/openstack-project-manager#67)
- Always create the domain admin user in the default domain (osism/openstack-project-manager#68)
- Create and assign an admin user by default (osism/openstack-project-manager#69)
- Rename manage_external_network_rbacs and correctly add or remove external network access based on project settings (osism/openstack-project-manager#72)
- Always grant the service project access to the public network (osism/openstack-project-manager#74)
- Improve logging output, levels and formatting (osism/openstack-project-manager#75, osism/openstack-project-manager#78, osism/openstack-project-manager#79)
- Rename domain network feature to service network (osism/openstack-project-manager#80)
- Always use the service quota class for the service project (osism/openstack-project-manager#82)
- Always use the default quota class for the images project and hide its public network (osism/openstack-project-manager#83, osism/openstack-project-manager#86)
- Manage service network access via RBAC policies instead of external network sharing (osism/openstack-project-manager#88)
- Stop managing endpoint filters by default, add manage-endpoints option to opt in (osism/openstack-project-manager#89)
- Increase testbed quotas for volumes and storage to support volume-based instances (osism/openstack-project-manager#103, osism/openstack-project-manager#104)
- Increase testbed volume quota for boot-from-volume support (osism/openstack-project-manager#123)
- Change license to AGPLv3 (osism/openstack-project-manager#126)
- Increase testbed quota to support more nodes and managerless deployment testing (osism/openstack-project-manager#127, osism/openstack-project-manager#132)
- Print user names in create-ldap script (osism/openstack-project-manager#128)
- Move documentation to osism/osism.github.io (osism/openstack-project-manager#141)
- Add Zuul job python-black and format Python files (osism/openstack-project-manager#143)
- Log project name and id during management runs (osism/openstack-project-manager#147)
- Use a default quota class when none is set (osism/openstack-project-manager#151)
- Handle the default quota class on okeanos projects (osism/openstack-project-manager#153)
- Adjust okeanos quota class limits (osism/openstack-project-manager#155)
- Increase storage quota for the okeanos class (osism/openstack-project-manager#158)
- Only assign member and load-balancer_member as default roles (osism/openstack-project-manager#159)
- Cache roles, admin domain, and admin users to reduce redundant API calls (osism/openstack-project-manager#160, osism/openstack-project-manager#161, osism/openstack-project-manager#162)
- Remove the limit on the number of instances since it is already constrained by VCPU and RAM quotas (osism/openstack-project-manager#172)
- Update documentation link from osism.github.io to osism.tech (osism/openstack-project-manager#171)
- Log the default quotaclass when none is set on a project (osism/openstack-project-manager#175)
- Update documentation link in README (osism/openstack-project-manager#177)
- Remove limits on instances, cores, ports and security group rules in the service class (osism/openstack-project-manager#181, osism/openstack-project-manager#182)
- Migrate CLI argument parsing from oslo_config to typer across manage.py, manage-ldap.py and create-user.py, restructure the scripts into the openstack_project_manager module, and add tox/zuul test automation (osism/openstack-project-manager#180)

### Fixed
- Fix missing project name in log message when attaching a subnet to a router (osism/openstack-project-manager@1e70c4f)
- Fix AttributeError handling when creating external and service network RBAC policies (osism/openstack-project-manager@49b4174)
- Fix typo in create.py CLI help text (osism/openstack-project-manager@f22f871)
- Fix RAM value of the testbed quota class (osism/openstack-project-manager@c5470d8)
- Add missing loguru import in manage.py (osism/openstack-project-manager@ec7435a)
- Ignore errors when granting roles that do not exist (osism/openstack-project-manager@4a66fff)
- Stop creating and assigning the keystone admin endpoint, which is no longer required (osism/openstack-project-manager@e9d612e, osism/openstack-project-manager@78589a3)
- Ignore non-existing endpoint groups when adding endpoints (osism/openstack-project-manager#65)
- Move log statement inside try/except block for endpoint assignment (osism/openstack-project-manager#66)
- Fix role assignment by removing invalid domain argument (osism/openstack-project-manager#70)
- Fix undefined domain_name variable in external network RBAC handling (osism/openstack-project-manager#73)
- Fix quota for images projects (osism/openstack-project-manager#84)
- Improve error handling in cache_images (osism/openstack-project-manager#109)
- Fix volume quota override using wrong quota class key (osism/openstack-project-manager#116)
- Fix some flake8 issues (osism/openstack-project-manager#138)
- Fix logging output for quota class checks (osism/openstack-project-manager#152)
- Prevent crash when a requested quota class is not found by safely handling missing quota class data in quota, network RBAC, and volume type checks (osism/openstack-project-manager#180)
- Fix incorrect domain name comparison that always evaluated as true, affecting router quota calculation and service network checks (osism/openstack-project-manager#180)
- Fix incorrect username extraction when matching home project users by project name (osism/openstack-project-manager#180)

### Removed
- Remove Travis CI integration (osism/openstack-project-manager@b941639)
- Remove magnum from the default orchestration endpoints (osism/openstack-project-manager@760da43)
- Remove test-requirements.txt and the related tox check environment (osism/openstack-project-manager@c4169ed)
- Remove testbed quota class (osism/openstack-project-manager@66e421c)
- Remove LBaaS v2 and FWaaS quotas from quota classes (osism/openstack-project-manager@4842620, osism/openstack-project-manager@1ba20d7)
- Remove PR Labeler GitHub workflow (osism/openstack-project-manager#18)
- Remove outdated add-user-to-project.sh and create-user.sh helper scripts (osism/openstack-project-manager@f404df3)
- Remove the panko endpoint from the telemetry service list (osism/openstack-project-manager@7a2355b)
- Remove old compute quotas (fixed_ips, floating_ips, security_groups, security_group_rules) from quota classes (osism/openstack-project-manager#64)
- Remove has-shared-router option (osism/openstack-project-manager#88)
- Remove release notes management, now handled centrally in osism/release and osism/osism.github.io (osism/openstack-project-manager#178)

### Dependencies
- python-neutronclient 7.2.1 → 7.3.0 (osism/openstack-project-manager#7)
- pyyaml 5.3.1 → 5.4 (osism/openstack-project-manager#8)
- pyyaml 5.4 → 5.4.1 (osism/openstack-project-manager#9)
- openstacksdk 0.52.0 → 0.53.0 (osism/openstack-project-manager#10)
- openstacksdk 0.53.0 → 0.54.0 (osism/openstack-project-manager#14)
- openstacksdk 0.54.0 → 0.55.0 (osism/openstack-project-manager#15)
- openstacksdk 0.55.0 → 0.56.0 (osism/openstack-project-manager#16)
- openstacksdk 0.56.0 → 0.61.0 (osism/openstack-project-manager#29)
- python-neutronclient 7.3.0 → 7.8.0 (osism/openstack-project-manager#30)
- actions/checkout v2 → v3 (osism/openstack-project-manager#32)
- actions/setup-python v2 → v3 (osism/openstack-project-manager#33)
- pyyaml 5.4.1 → 6.0 (osism/openstack-project-manager#34)
- openstacksdk 0.61.0 → 0.99.0 (osism/openstack-project-manager#35)
- actions/setup-python v3 → v4 (osism/openstack-project-manager#36)
- openstacksdk 0.99.0 → 0.100.0 (osism/openstack-project-manager#37)
- python-neutronclient 7.8.0 → 8.0.0 (osism/openstack-project-manager#38)
- openstacksdk 0.100.0 → 0.101.0 (osism/openstack-project-manager#39)
- python-neutronclient 8.0.0 → 8.1.0 (osism/openstack-project-manager#40)
- openstacksdk 0.101.0 → 0.102.0 (osism/openstack-project-manager#41)
- python-neutronclient 8.1.0 → 8.2.0 (osism/openstack-project-manager#42)
- openstacksdk 0.102.0 → 0.103.0 (osism/openstack-project-manager#43)
- python-neutronclient 8.2.0 → 8.2.1 (osism/openstack-project-manager#44)
- python-neutronclient 8.2.1 → 9.0.0 (osism/openstack-project-manager#47)
- openstacksdk 0.103.0 → 1.0.1 (osism/openstack-project-manager#45)
- loguru 0.6.0 → 0.7.0 (osism/openstack-project-manager#93)
- openstacksdk 1.0.1 → 1.2.0 (osism/openstack-project-manager#97, osism/openstack-project-manager#100)
- python-neutronclient 9.0.0 → 10.0.0 (osism/openstack-project-manager#98)
- cryptography 40.0.2 → 41.0.0 (osism/openstack-project-manager#102)
- openstacksdk 1.2.0 → 1.3.0 (osism/openstack-project-manager#105)
- openstacksdk 1.3.0 → 1.3.1 (osism/openstack-project-manager#107)
- python-neutronclient 10.0.0 → 11.0.0 (osism/openstack-project-manager#113)
- dynaconf 3.1.12 → 3.2.0 (osism/openstack-project-manager#114)
- pyyaml 6.0 → 6.0.1 (osism/openstack-project-manager#115)
- certifi 2023.5.7 → 2023.7.22 (osism/openstack-project-manager#117)
- cryptography 41.0.2 → 41.0.3 (osism/openstack-project-manager#118)
- openstacksdk 1.3.1 → 1.5.0 (osism/openstack-project-manager#119, osism/openstack-project-manager#124)
- dynaconf 3.2.0 → 3.2.2 (osism/openstack-project-manager#121, osism/openstack-project-manager#122)
- loguru 0.7.0 → 0.7.1 (osism/openstack-project-manager#125)
- loguru 0.7.1 → 0.7.2 (osism/openstack-project-manager#129)
- dynaconf 3.2.2 → 3.2.3 (osism/openstack-project-manager#130)
- openstacksdk 1.5.0 → 2.0.0 (osism/openstack-project-manager#137)
- dynaconf 3.2.3 → 3.2.4 (osism/openstack-project-manager#140)
- python-neutronclient 11.0.0 → 11.1.0 (osism/openstack-project-manager#144)
- python-ldap 3.4.3 → 3.4.4 (osism/openstack-project-manager#145)
- cryptography 41.0.5 → 41.0.6 (osism/openstack-project-manager#148)
- deepmerge 1.1.0 → 1.1.1 (osism/openstack-project-manager#163)
- openstacksdk 2.0.0 → 2.1.0 (osism/openstack-project-manager#164)
- openstacksdk 2.1.0 → 3.0.0 (osism/openstack-project-manager#168)
- python-neutronclient 11.1.0 → 11.2.0 (osism/openstack-project-manager#169)
- dynaconf 3.2.4 → 3.2.5 (osism/openstack-project-manager#170)
- openstacksdk 3.0.0 → 3.1.0 (osism/openstack-project-manager#174)
- python-neutronclient 11.2.0 → 11.3.0 (osism/openstack-project-manager#176)
- openstacksdk 3.1.0 → 3.2.0 (osism/openstack-project-manager#184)
- python-neutronclient 11.3.0 → 11.3.1 (osism/openstack-project-manager#183)
- typer 0.9.0 → 0.12.3 (osism/openstack-project-manager#185)

