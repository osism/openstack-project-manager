import unittest
from unittest.mock import MagicMock, patch, ANY, call

import string

import typer
from typer.testing import CliRunner

from openstack_project_manager.create import generate_password, run


app = typer.Typer()
app.command()(run)


class TestUtils(unittest.TestCase):

    def test_utils_0(self):
        password = generate_password(10)
        assert isinstance(password, str)
        assert len(password) == 10
        for char in password:
            assert char in (string.ascii_letters + string.digits)

        password2 = generate_password(10)
        assert isinstance(password2, str)
        assert len(password2) == 10
        for char in password2:
            assert char in (string.ascii_letters + string.digits)

        assert password != password2

        assert len(generate_password(100)) == 100
        assert len(generate_password(1)) == 1
        assert len(generate_password(0)) == 0
        assert len(generate_password(-1)) == 0


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.patcher = patch("openstack.connect")
        self.mock_connect = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.mock_os_cloud = MagicMock()
        self.mock_connect.return_value = self.mock_os_cloud
        self.mock_os_domain = MagicMock()
        self.mock_os_domain.id = 1234
        self.mock_os_cloud.identity.find_domain.return_value = self.mock_os_domain
        self.mock_os_user = MagicMock()
        self.mock_os_user.id = 5678
        self.mock_os_cloud.identity.find_user.return_value = self.mock_os_user
        self.mock_os_project = MagicMock()
        self.mock_os_project.id = 9012
        self.mock_os_cloud.identity.find_project.return_value = self.mock_os_project

        self.os_roles = []
        for rolename in ["member", "load-balancer_member"]:
            role = MagicMock()
            role.name = rolename
            role.id = len(self.os_roles)
            self.os_roles.append(role)
        self.mock_os_cloud.identity.roles.return_value = self.os_roles

        self.patcher2 = patch("openstack_project_manager.create.generate_password")
        self.mock_generate_password = self.patcher2.start()
        self.addCleanup(self.patcher2.stop)
        self.mock_generate_password.return_value = "randompassword"

        self.patcher3 = patch("os_client_config.make_client")
        self.mock_make_client = self.patcher3.start()
        self.addCleanup(self.patcher3.stop)
        self.mock_os_keystone = MagicMock()
        self.mock_make_client.return_value = self.mock_os_keystone

        self.runner = CliRunner()

    def test_cli_0(self):
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))
        self.mock_connect.assert_not_called()

    def test_cli_1(self):
        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_connect.assert_called_once_with(cloud="admin")
        self.mock_generate_password.assert_called_once_with(16)
        self.mock_os_cloud.identity.find_domain.assert_any_call("default")
        self.mock_os_cloud.identity.find_project.assert_called_once_with(
            "default-sandbox", domain_id=1234
        )

        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quotaclass="basic"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quotamultiplier=1
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, has_service_network="False"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, service_network_cidr=""
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, has_public_network="True"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, show_public_network="True"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, public_network="public"
        )

        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, has_shared_images="True"
        )
        self.mock_os_keystone.projects.update.assert_any_call(project=9012, owner="")

        self.mock_os_cloud.identity.find_user.assert_called_once_with(
            "default-admin", domain_id=1234
        )

        for role in self.os_roles:
            self.mock_os_cloud.identity.assign_project_role_to_user.assert_any_call(
                self.mock_os_project.id, self.mock_os_user.id, role.id
            )

    def test_cli_2(self):
        self.mock_os_cloud.identity.find_domain.return_value = None
        mock_os_domain = MagicMock()
        mock_os_domain.id = 5678
        self.mock_os_cloud.create_domain.return_value = mock_os_domain

        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_domain.assert_any_call("default")
        self.mock_os_cloud.create_domain.assert_called_with(name="default")
        self.mock_os_cloud.identity.find_project.assert_called_once_with(
            "default-sandbox", domain_id=5678
        )

    def test_cli_3(self):
        self.mock_os_cloud.identity.find_project.return_value = None
        mock_os_project = MagicMock()
        mock_os_project.id = 1111
        self.mock_os_cloud.create_project.return_value = mock_os_project

        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.create_project.assert_called_once_with(
            name="default-sandbox", domain_id=1234
        )

        self.mock_os_keystone.projects.update.assert_any_call(
            project=1111, quotaclass="basic"
        )

    def test_cli_4(self):
        self.mock_os_cloud.identity.find_user.return_value = None
        mock_os_user = MagicMock()
        mock_os_user.id = 2222
        self.mock_os_cloud.create_user.return_value = mock_os_user

        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.create_user.assert_called_once_with(
            name="default-admin", password=ANY, domain_id=1234
        )

        for role in self.os_roles:
            self.mock_os_cloud.identity.assign_project_role_to_user.assert_any_call(
                self.mock_os_project.id, mock_os_user.id, role.id
            )

    def test_cli_5(self):
        result = self.runner.invoke(app, ["--noassign-admin-user"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_user.assert_not_called()
        self.mock_os_cloud.identity.assign_project_role_to_user.assert_not_called()

    def test_cli_6(self):
        self.mock_os_cloud.identity.find_user.return_value = None
        mock_os_user = MagicMock()
        mock_os_user.id = 2222
        self.mock_os_cloud.create_user.return_value = mock_os_user

        result = self.runner.invoke(app, ["--nocreate-admin-user"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.create_user.assert_not_called()
        self.mock_os_cloud.identity.assign_project_role_to_user.assert_not_called()

    def test_cli_7(self):
        result = self.runner.invoke(app, ["--create-domain"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_project.assert_not_called()
        self.mock_os_keystone.projects.update.assert_not_called()
        self.mock_os_cloud.identity.assign_project_role_to_user.assert_not_called()

    def test_cli_8(self):
        result = self.runner.invoke(app, ["--create-user"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_user.assert_any_call(
            "default-sandbox", domain_id=1234
        )
        self.mock_os_cloud.update_user.assert_called_once_with(
            self.mock_os_user, password=ANY
        )

    def test_cli_9(self):
        result = self.runner.invoke(app, ["--nodomain-name-prefix"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_project.assert_called_once_with(
            "sandbox", domain_id=1234
        )

    def test_cli_10(self):
        result = self.runner.invoke(
            app,
            [
                "--has-service-network",
                "--nohas-public-network",
                "--nohas-shared-images",
                "--managed-network-resources",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, has_service_network="True"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, has_public_network="False"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, show_public_network="False"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, has_shared_images="False"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, managed_network_resources="True"
        )

    def test_cli_11(self):
        result = self.runner.invoke(app, ["--random", "--password-length=25"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_generate_password.assert_called_once_with(25)
        self.mock_os_cloud.identity.find_project.assert_called_once()
        assert (
            call("default-sandbox", domain_id=1234)
            not in self.mock_os_cloud.identity.find_project.mock_calls
        )

    def test_cli_12(self):
        result = self.runner.invoke(
            app,
            [
                "--quota-multiplier=2",
                "--quota-multiplier-compute=3",
                "--quota-multiplier-network=4",
                "--quota-multiplier-storage=5",
                "--quota-router=6",
                "--quota-class=notbasic",
                "--service-network-cidr=othercidr",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quotaclass="notbasic"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quotamultiplier=2
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quotamultiplier_compute=3
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quotamultiplier_network=4
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quotamultiplier_storage=5
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, quota_router=6
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, service_network_cidr="othercidr"
        )

    def test_cli_13(self):
        result = self.runner.invoke(
            app,
            [
                "--admin-domain=otheradmin",
                "--cloud=othercloud",
                "--domain=otherdomain",
                "--internal-id=abcd",
                "--name=othername",
                "--owner=otherowner",
                "--public-network=otherpublic",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_connect.assert_called_once_with(cloud="othercloud")
        self.mock_os_cloud.identity.find_domain.assert_any_call("otherdomain")
        self.mock_os_cloud.identity.find_project.assert_called_once_with(
            "otherdomain-othername", domain_id=1234
        )

        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, internal_id="abcd"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, public_network="otherpublic"
        )
        self.mock_os_keystone.projects.update.assert_any_call(
            project=9012, owner="otherowner"
        )
        self.mock_os_cloud.identity.find_user.assert_called_once_with(
            "otherdomain-admin", domain_id=1234
        )

    def test_cli_14(self):
        result = self.runner.invoke(app, ["--password=otherpassword", "--create-user"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_generate_password.assert_not_called()
        self.mock_os_cloud.update_user.assert_called_once_with(
            self.mock_os_user, password="otherpassword"
        )


if __name__ == "__main__":
    unittest.main()
