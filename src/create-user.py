# SPDX-License-Identifier: AGPL-3.0-or-later

import random
import string

import typer
import openstack
from tabulate import tabulate


# Default roles to be assigned to a new user for a project
DEFAULT_ROLES = ["member", "load-balancer_member"]


def generate_password(password_length: int) -> str:
    return "".join(
        random.choice(string.ascii_letters + string.digits)
        for x in range(password_length)
    )


def run(
    random: bool = typer.Option(False, "--random", help="Generate random names"),
    domain_name_prefix: bool = typer.Option(
        True,
        "--domain-name-prefix",
        help="Add domain name as prefix to the project name",
    ),
    password_length: int = typer.Option(
        16, "--password-length", help="Password length"
    ),
    cloud_name: str = typer.Option("admin", "--cloud", help="Managed cloud"),
    domain_name: str = typer.Option("default", "--domain", help="Domain"),
    name: str = typer.Option("", "--name", help="Username"),
    project_name: str = typer.Option("", "--project-name", help="Projectname"),
    password: str = typer.Option(None, "--password", help="Password"),
) -> None:

    # Connect to the OpenStack environment
    os_cloud = openstack.connect(cloud=cloud_name)

    # cache roles
    CACHE_ROLES = {}
    for role in os_cloud.identity.roles():
        CACHE_ROLES[role.name] = role

    # Generate a random password from all ASCII characters + digits
    if not password:
        password = generate_password(password_length)

    # Establish dedicated connection to Keystone service
    # FIXME(berendt): use get_domain
    domain = os_cloud.identity.find_domain(domain_name)
    if not domain:
        domain = os_cloud.create_domain(name=domain_name)

    # Find or create the user
    # FIXME(berendt): use get_project
    if domain_name_prefix:
        project = os_cloud.identity.find_project(
            f"{domain_name}-{project_name}", domain_id=domain.id
        )
    else:
        project = os_cloud.identity.find_project(project_name, domain_id=domain.id)

    user = os_cloud.identity.find_user(name, domain_id=domain.id)
    if not user:
        user = os_cloud.create_user(
            name=name,
            password=password,
            default_project=project,
            domain_id=domain.id,
        )
    else:
        os_cloud.update_user(user, password=password)

    for role_name in DEFAULT_ROLES:
        try:
            role = CACHE_ROLES[role_name]
            os_cloud.identity.assign_project_role_to_user(project.id, user.id, role.id)
        except:
            pass

    result = [
        ["domain", domain_name, domain.id],
        ["project", project_name, project.id],
    ]

    result.append(["user", name, user.id])
    result.append(["password", password, ""])

    print(tabulate(result, headers=["name", "value", "id"], tablefmt="psql"))


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
