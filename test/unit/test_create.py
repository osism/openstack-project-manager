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

        # Mock for user connection (second openstack.connect call)
        self.mock_user_cloud = MagicMock()
        self.mock_app_cred = MagicMock()
        self.mock_app_cred.id = "app-cred-id-123"
        self.mock_app_cred.secret = "app-cred-secret-456"
        self.mock_user_cloud.identity.create_application_credential.return_value = (
            self.mock_app_cred
        )

        # Mock config for auth_url retrieval
        self.mock_os_cloud.config.get_auth_args.return_value = {
            "auth_url": "https://keystone.example.com:5000/v3"
        }
        self.mock_os_cloud.config.region_name = "RegionOne"
        self.mock_os_cloud.config.get_interface.return_value = "public"

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
        # Set up a side_effect to handle multiple find_domain calls
        # First call for regular domain returns None (domain doesn't exist)
        # Second call for admin domain returns the mock (admin domain exists)
        mock_os_domain = MagicMock()
        mock_os_domain.id = 5678
        mock_admin_domain = MagicMock()
        mock_admin_domain.id = "admin-domain-id"
        mock_admin_domain.name = "admin-domain"

        def find_domain_side_effect(name):
            if name == "default":
                # After first call, domain is created, so return the created domain
                return (
                    mock_os_domain if self.mock_os_cloud.create_domain.called else None
                )
            else:  # admin domain
                return mock_admin_domain

        self.mock_os_cloud.identity.find_domain.side_effect = find_domain_side_effect
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

    def test_cli_15(self):
        """Test application credential creation with --create-user flag"""
        # Setup: User doesn't exist, needs to be created
        self.mock_os_cloud.identity.find_user.return_value = None
        mock_os_user = MagicMock()
        mock_os_user.id = "user-id-789"
        self.mock_os_cloud.create_user.return_value = mock_os_user

        # Setup: Second connect() call returns user connection
        self.mock_connect.side_effect = [self.mock_os_cloud, self.mock_user_cloud]

        result = self.runner.invoke(
            app,
            [
                "--create-user",
                "--create-application-credential",
                "--noassign-admin-user",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        # Verify user was created
        self.mock_os_cloud.create_user.assert_called_once()

        # Verify second connection as user
        self.assertEqual(self.mock_connect.call_count, 2)
        user_connect_call = self.mock_connect.call_args_list[1]
        user_config = user_connect_call[1]

        # Verify user connection config
        self.assertEqual(user_config["auth"]["username"], "default-sandbox")
        self.assertEqual(user_config["auth"]["password"], "randompassword")
        self.assertEqual(user_config["auth"]["project_name"], "default-sandbox")
        self.assertEqual(user_config["auth"]["project_domain_name"], "default")
        self.assertEqual(user_config["auth"]["user_domain_name"], "default")
        self.assertEqual(
            user_config["auth"]["auth_url"], "https://keystone.example.com:5000/v3"
        )
        self.assertEqual(user_config["region_name"], "RegionOne")
        self.assertEqual(user_config["interface"], "public")

        # Verify application credential was created
        self.mock_user_cloud.identity.create_application_credential.assert_called_once_with(
            user=mock_os_user.id, name="default-sandbox"
        )

        # Verify output contains application credential info
        self.assertIn("application_credential_id", result.stdout)
        self.assertIn("app-cred-id-123", result.stdout)
        self.assertIn("application_credential_secret", result.stdout)
        self.assertIn("app-cred-secret-456", result.stdout)

    def test_cli_16(self):
        """Test application credential flag without --create-user shows warning"""
        with patch("openstack_project_manager.create.logger") as mock_logger:
            result = self.runner.invoke(app, ["--create-application-credential"])
            self.assertEqual(result.exit_code, 0, (result, result.stdout))

            # Verify warning was logged
            mock_logger.warning.assert_called_once_with(
                "Application credential creation requires --create-user flag"
            )

            # Verify no application credential output
            self.assertNotIn("application_credential_id", result.stdout)
            self.assertNotIn("application_credential_secret", result.stdout)

            # Verify only one connection (admin), no user connection
            self.assertEqual(self.mock_connect.call_count, 1)

    def test_cli_17(self):
        """Test graceful error handling when application credential creation fails"""
        # Setup: User needs to be created
        self.mock_os_cloud.identity.find_user.return_value = None
        mock_os_user = MagicMock()
        mock_os_user.id = "user-id-789"
        self.mock_os_cloud.create_user.return_value = mock_os_user

        # Setup: User connection succeeds but app cred creation fails
        self.mock_user_cloud.identity.create_application_credential.side_effect = (
            Exception("API Error")
        )
        self.mock_connect.side_effect = [self.mock_os_cloud, self.mock_user_cloud]

        with patch("openstack_project_manager.create.logger") as mock_logger:
            result = self.runner.invoke(
                app,
                [
                    "--create-user",
                    "--create-application-credential",
                    "--noassign-admin-user",
                ],
            )
            self.assertEqual(result.exit_code, 0, (result, result.stdout))

            # Verify error was logged
            mock_logger.error.assert_called_once()
            error_call_args = mock_logger.error.call_args[0][0]
            self.assertIn("Failed to create application credential", error_call_args)

            # Verify no application credential in output (graceful degradation)
            self.assertNotIn("application_credential_id", result.stdout)
            self.assertNotIn("application_credential_secret", result.stdout)

    def test_cli_18(self):
        """Test application credential with custom name and domain"""
        # Setup
        self.mock_os_cloud.identity.find_user.return_value = None
        mock_os_user = MagicMock()
        mock_os_user.id = "user-id-custom"
        self.mock_os_cloud.create_user.return_value = mock_os_user
        self.mock_connect.side_effect = [self.mock_os_cloud, self.mock_user_cloud]

        result = self.runner.invoke(
            app,
            [
                "--create-user",
                "--create-application-credential",
                "--name=myproject",
                "--domain=mydomain",
                "--noassign-admin-user",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        # Verify user connection uses custom values
        user_connect_call = self.mock_connect.call_args_list[1]
        user_config = user_connect_call[1]
        self.assertEqual(user_config["auth"]["username"], "mydomain-myproject")
        self.assertEqual(user_config["auth"]["project_name"], "mydomain-myproject")
        self.assertEqual(user_config["auth"]["project_domain_name"], "mydomain")
        self.assertEqual(user_config["auth"]["user_domain_name"], "mydomain")

        # Verify application credential uses custom name
        self.mock_user_cloud.identity.create_application_credential.assert_called_once_with(
            user=mock_os_user.id, name="mydomain-myproject"
        )


if __name__ == "__main__":
    unittest.main()
