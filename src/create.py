# SPDX-License-Identifier: AGPL-3.0-or-later

import random
import string
import sys

from loguru import logger
import typer
import os_client_config
import openstack
from tabulate import tabulate


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


def run(
    assign_admin_user: bool = typer.Option(
        True, "--assign-admin-user", help="Assign admin user"
    ),
    create_admin_user: bool = typer.Option(
        True, "--create-admin-user", help="Create admin user"
    ),
    create_domain: bool = typer.Option(
        False, "--create-domain", help="Create domain only"
    ),
    create_user: bool = typer.Option(False, "--create-user", help="Create user"),
    domain_name_prefix: bool = typer.Option(
        True,
        "--domain-name-prefix",
        help="Add domain name as prefix to the project name",
    ),
    has_service_network: bool = typer.Option(
        False, "--has-service-network", help="Has service network infrastructure"
    ),
    has_public_network: bool = typer.Option(
        True, "--has-public-network", help="Has public network infrastructure"
    ),
    has_shared_images: bool = typer.Option(
        True, "--has-shared-images", help="Has shared images"
    ),
    use_random: bool = typer.Option(False, "--random", help="Generate random names"),
    managed_network_resources: bool = typer.Option(
        False, "--managed-network-resources", help="Manage the network resources"
    ),
    password_length: int = typer.Option(
        16, "--password-length", help="Password length"
    ),
    quota_multiplier: int = typer.Option(
        "1", "--quota-multiplier", help="Quota multiplier"
    ),
    quota_multiplier_compute: int = typer.Option(
        None, "--quota-multiplier-compute", help="Quota multiplier compute"
    ),
    quota_multiplier_network: int = typer.Option(
        None, "--quota-multiplier-network", help="Quota multiplier network"
    ),
    quota_multiplier_storage: int = typer.Option(
        None, "--quota-multiplier-storage", help="Quota multiplier storage"
    ),
    quota_router: int = typer.Option(1, "--quota-router", help="Quota router"),
    admin_domain: str = typer.Option("default", "--admin-domain", help="Admin domain"),
    cloud_name: str = typer.Option("admin", "--cloud", help="Managed cloud"),
    domain_name: str = typer.Option("default", "--domain", help="Domain"),
    internal_id: str = typer.Option(None, "--internal-id", help="Internal ID"),
    name: str = typer.Option("sandbox", "--name", help="Projectname"),
    owner: str = typer.Option("", "--owner", help="Owner of the project"),
    password: str = typer.Option(None, "--password", help="Password"),
    public_network: str = typer.Option(
        "public", "--public-network", help="Public network"
    ),
    quota_class: str = typer.Option("basic", "--quota-class", help="Quota class"),
    service_network_cidr: str = typer.Option(
        "", "--service-network-cidr", help="Service network CIDR"
    ),
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
        part2 = f"{random.randint(0,9999):04d}"
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
                try:
                    role = CACHE_ROLES[role_name]
                    os_cloud.identity.assign_project_role_to_user(
                        project.id, user.id, role.id
                    )
                except:
                    pass

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
                    try:
                        role = CACHE_ROLES["domain-manager"]
                        os_cloud.identity.assign_domain_role_to_user(
                            domain.id, admin_user.id, role.id
                        )
                    except:
                        pass

            if admin_user and not create_domain:
                for role_name in DEFAULT_ADMIN_ROLES:
                    try:
                        role = CACHE_ROLES[role_name]
                        os_cloud.identity.assign_project_role_to_user(
                            project.id, admin_user.id, role.id
                        )
                    except:
                        pass

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
