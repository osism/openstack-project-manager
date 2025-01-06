# SPDX-License-Identifier: AGPL-3.0-or-later

import random
import string
import sys

from loguru import logger
import typer
from typing_extensions import Annotated
import os_client_config
import openstack
from tabulate import tabulate
from typing import Optional


# Default roles to be assigned to a new user for a project
DEFAULT_ROLES = ["member", "load-balancer_member"]

# Default roles to be assigned to a admin user for a project
DEFAULT_ADMIN_ROLES = [
    "member",
    "load-balancer_member",
]

logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>"
logger.remove()
logger.add(sys.stdout, format=logger_format)


def generate_password(password_length: int) -> str:
    return "".join(
        random.choice(string.ascii_letters + string.digits)
        for x in range(password_length)
    )


def try_assign_role(
    os_cloud: openstack.connection.Connection,
    project: openstack.identity.v3.project.Project,
    user: openstack.identity.v3.user.User,
    role: openstack.identity.v3.role.Role,
) -> None:
    try:
        os_cloud.identity.assign_project_role_to_user(project.id, user.id, role.id)
    except:
        pass


def run(
    assign_admin_user: Annotated[
        bool,
        typer.Option(
            "--assign-admin-user/--noassign-admin-user", help="Assign admin user"
        ),
    ] = True,
    create_admin_user: Annotated[
        bool,
        typer.Option(
            "--create-admin-user/--nocreate-admin-user", help="Create admin user"
        ),
    ] = True,
    create_domain: Annotated[
        bool,
        typer.Option("--create-domain/--nocreate-domain", help="Create domain only"),
    ] = False,
    create_user: Annotated[
        bool, typer.Option("--create-user/--nocreate-user", help="Create user")
    ] = False,
    domain_name_prefix: Annotated[
        bool,
        typer.Option(
            "--domain-name-prefix/--nodomain-name-prefix",
            help="Add domain name as prefix to the project name",
        ),
    ] = True,
    has_service_network: Annotated[
        bool,
        typer.Option(
            "--has-service-network/--nohas-service-network",
            help="Has service network infrastructure",
        ),
    ] = False,
    has_public_network: Annotated[
        bool,
        typer.Option(
            "--has-public-network/--nohas-public-network",
            help="Has public network infrastructure",
        ),
    ] = True,
    has_shared_images: Annotated[
        bool,
        typer.Option(
            "--has-shared-images/--nohas-shared-images", help="Has shared images"
        ),
    ] = True,
    use_random: Annotated[
        bool, typer.Option("--random/--norandom", help="Generate random names")
    ] = False,
    managed_network_resources: Annotated[
        bool,
        typer.Option(
            "--managed-network-resources/--nomanaged-network-resources",
            help="Manage the network resources",
        ),
    ] = False,
    password_length: Annotated[
        int, typer.Option("--password-length", help="Password length")
    ] = 16,
    quota_multiplier: Annotated[
        int, typer.Option("--quota-multiplier", help="Quota multiplier")
    ] = 1,
    quota_multiplier_compute: Annotated[
        Optional[int],
        typer.Option("--quota-multiplier-compute", help="Quota multiplier compute"),
    ] = None,
    quota_multiplier_network: Annotated[
        Optional[int],
        typer.Option("--quota-multiplier-network", help="Quota multiplier network"),
    ] = None,
    quota_multiplier_storage: Annotated[
        Optional[int],
        typer.Option("--quota-multiplier-storage", help="Quota multiplier storage"),
    ] = None,
    quota_router: Annotated[
        int, typer.Option("--quota-router", help="Quota router")
    ] = 1,
    admin_domain: Annotated[
        str, typer.Option("--admin-domain", help="Admin domain")
    ] = "default",
    cloud_name: Annotated[str, typer.Option("--cloud", help="Managed cloud")] = "admin",
    domain_name: Annotated[str, typer.Option("--domain", help="Domain")] = "default",
    internal_id: Annotated[
        Optional[str], typer.Option("--internal-id", help="Internal ID")
    ] = None,
    name: Annotated[str, typer.Option("--name", help="Projectname")] = "sandbox",
    owner: Annotated[str, typer.Option("--owner", help="Owner of the project")] = "",
    password: Annotated[
        Optional[str], typer.Option("--password", help="Password")
    ] = None,
    public_network: Annotated[
        str, typer.Option("--public-network", help="Public network")
    ] = "public",
    quota_class: Annotated[
        str, typer.Option("--quota-class", help="Quota class")
    ] = "basic",
    service_network_cidr: Annotated[
        str, typer.Option("--service-network-cidr", help="Service network CIDR")
    ] = "",
) -> None:

    # Connect to the OpenStack environment
    os_cloud = openstack.connect(cloud=cloud_name)

    # cache roles
    CACHE_ROLES = {}
    for role in os_cloud.identity.roles():
        CACHE_ROLES[role.name] = role

    # Generate a random name in the form abcd-0123
    if use_random:
        part1 = "".join(random.choice(string.ascii_letters) for x in range(4)).lower()
        part2 = f"{random.randint(0, 9999):04d}"
        name = f"{part1}-{part2}"

    # Add the domain name as a prefix to the name
    if domain_name_prefix:
        name = f"{domain_name}-{name}"

    # Generate a random password from all ASCII characters + digits
    if not password:
        password = generate_password(password_length)

    # Establish dedicated connection to Keystone service
    # FIXME(berendt): use get_domain
    domain_created = False
    domain = os_cloud.identity.find_domain(domain_name)
    if not domain:
        domain = os_cloud.create_domain(name=domain_name)
        domain_created = True

    # Find or create the project
    if not create_domain:
        # FIXME(berendt): use get_project
        project = os_cloud.identity.find_project(name, domain_id=domain.id)
        if not project:
            project = os_cloud.create_project(name=name, domain_id=domain.id)

        # FIXME(berendt): use openstacksdk
        keystone = os_client_config.make_client("identity", cloud=cloud_name)

        # Set the quota parameters of the project
        keystone.projects.update(project=project.id, quotaclass=quota_class)
        keystone.projects.update(project=project.id, quotamultiplier=quota_multiplier)
        if quota_multiplier_compute:
            keystone.projects.update(
                project=project.id, quotamultiplier_compute=quota_multiplier_compute
            )
        if quota_multiplier_network:
            keystone.projects.update(
                project=project.id, quotamultiplier_network=quota_multiplier_network
            )
        if quota_multiplier_storage:
            keystone.projects.update(
                project=project.id, quotamultiplier_storage=quota_multiplier_storage
            )
        if quota_router:
            keystone.projects.update(project=project.id, quota_router=quota_router)

        # Set network parameters of the project
        keystone.projects.update(
            project=project.id, has_service_network=str(has_service_network)
        )
        keystone.projects.update(
            project=project.id, service_network_cidr=str(service_network_cidr)
        )
        keystone.projects.update(
            project=project.id, has_public_network=str(has_public_network)
        )
        keystone.projects.update(
            project=project.id,
            show_public_network=str(has_public_network),
        )
        keystone.projects.update(project=project.id, public_network=public_network)

        if name == "service":
            # Tag service projects
            keystone.projects.update(project=project.id, is_service_project=str(True))

            # For a service project always use the quota class service
            keystone.projects.update(project=project.id, quotaclass="service")

        if name == "images":
            # For an images project always use the quota class default
            keystone.projects.update(project=project.id, quotaclass="images")
            keystone.projects.update(project=project.id, quota_router=0)
            # Only non-images projects can have shared images
            keystone.projects.update(project=project.id, has_shared_images=str(False))
            keystone.projects.update(project=project.id, has_public_network=str(False))
            keystone.projects.update(
                project=project.id,
                show_public_network=str(False),
            )
        else:
            keystone.projects.update(
                project=project.id, has_shared_images=str(has_shared_images)
            )

        # Set other parameters of the project
        keystone.projects.update(project=project.id, owner=owner)

        # The network resources of the project should be created automatically
        if managed_network_resources:
            keystone.projects.update(
                project=project.id, managed_network_resources="True"
            )

        if internal_id:
            keystone.projects.update(project=project.id, internal_id=internal_id)

        # Find or create the user of the project and assign the default roles
        if create_user:
            user = os_cloud.identity.find_user(name, domain_id=domain.id)
            if not user:
                user = os_cloud.create_user(
                    name=name,
                    password=password,
                    default_project=project,
                    domain_id=domain.id,
                    email=owner,
                )
            else:
                os_cloud.update_user(user, password=password)

            for role_name in DEFAULT_ROLES:
                try_assign_role(os_cloud, project, user, CACHE_ROLES[role_name])

    # Assign the domain admin user to the project
    admin_password = None
    admin_name = f"{domain_name}-admin"

    if assign_admin_user:
        os_admin_domain = os_cloud.identity.find_domain(admin_domain)
        if not os_admin_domain:
            logger.error(f"Admin domain {admin_domain} not found")
        else:
            admin_domain_id = os_admin_domain.id
            admin_user = os_cloud.identity.find_user(
                admin_name, domain_id=admin_domain_id
            )

            if not admin_user and create_admin_user:
                admin_password = generate_password(password_length)
                admin_user = os_cloud.create_user(
                    name=admin_name, password=admin_password, domain_id=admin_domain_id
                )

                if domain_created:
                    try_assign_role(
                        os_cloud, project, admin_user, CACHE_ROLES["domain-manager"]
                    )

            if admin_user and not create_domain:
                for role_name in DEFAULT_ADMIN_ROLES:
                    try_assign_role(
                        os_cloud, project, admin_user, CACHE_ROLES[role_name]
                    )

    result = [
        ["domain", domain_name, domain.id],
    ]

    if not create_domain:
        result.append(["project", name, project.id])

    # Outputs details about the domain admin user
    if create_admin_user and admin_password:
        result.append(["admin", admin_name, admin_user.id])
        result.append(["admin_password", admin_password, ""])

    # Outputs details about the project user
    if create_user and not create_domain:
        result.append(["user", name, user.id])
        result.append(["password", password, ""])

    print(tabulate(result, headers=["name", "value", "id"], tablefmt="psql"))


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
