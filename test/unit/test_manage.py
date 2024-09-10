import unittest
from unittest.mock import MagicMock, patch, ANY

import copy
import yaml

import typer
from typer.testing import CliRunner

from openstack_project_manager.manage import (
    Configuration,
    get_quotaclass,
    check_bool,
    check_quota,
    update_bandwidth_policy_rule,
    manage_external_network_rbacs,
    check_volume_types,
    check_bandwidth_limit,
    manage_private_volumetypes,
    create_network_resources,
    add_service_network,
    del_service_network,
    add_external_network,
    del_external_network,
    create_service_network,
    create_network,
    create_network_with_router,
    check_homeproject_permissions,
    assign_admin_user,
    check_endpoints,
    share_image_with_project,
    share_images,
    cache_images,
    process_project,
    handle_unmanaged_project,
    run,
)


app = typer.Typer()
app.command()(run)

MOCK_QUOTA_CLASSES = yaml.safe_load(
    """
---
default:
  compute:
    cores: 1
    injected_file_content_bytes: 10240
    instances: 255
  network:
    floatingip: 1
    network: 1
    router: 1
  volume:
    backup_gigabytes: 1
    backups: 1
    gigabytes: 1


unlimited:
  parent: default
  compute:
    cores: -1


volume_test:
  parent: default
  volume_types:
    item1:
      name: name
"""
)


class CloudTest(unittest.TestCase):

    def setUp(self):
        self.patcher = patch("openstack.connect")
        self.mock_connect = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.mock_os_cloud = MagicMock()
        self.mock_connect.return_value = self.mock_os_cloud

        self.mock_os_keystone = MagicMock()
        self.mock_os_neutron = MagicMock()

        def mock_make_client(name: str, cloud: str):
            if name == "identity":
                return self.mock_os_keystone
            elif name == "network":
                return self.mock_os_neutron

        self.patcher2 = patch("os_client_config.make_client")
        self.mock_make_client = self.patcher2.start()
        self.mock_make_client.side_effect = mock_make_client
        self.addCleanup(self.patcher2.stop)

        self.os_roles = []
        for rolename in ["member", "load-balancer_member"]:
            role = MagicMock()
            role.name = rolename
            role.id = len(self.os_roles)
            self.os_roles.append(role)
        self.mock_os_cloud.identity.roles.return_value = self.os_roles


class TestConfiguration(CloudTest):

    def setUp(self):
        super().setUp()
        self.patcher3 = patch("builtins.open")
        self.mock_open = self.patcher3.start()
        self.addCleanup(self.patcher3.stop)

        self.patcher4 = patch("yaml.load")
        self.mock_yaml_load = self.patcher4.start()
        self.addCleanup(self.patcher4.stop)
        self.mock_yaml_load.return_value = ["a", "b", "c"]

    def test_configuration_0(self):
        config = Configuration(
            False, "cloud-name", "endpoints.yml", True, "admin-domain"
        )

        assert not config.dry_run
        assert config.ENDPOINTS == ["a", "b", "c"]
        self.mock_connect.assert_called_once_with(cloud="cloud-name")
        assert config.os_cloud is self.mock_os_cloud
        assert config.os_keystone is self.mock_os_keystone
        assert config.os_neutron is self.mock_os_neutron
        assert len(config.CACHE_ROLES) > 0
        assert config.assign_admin_user
        self.mock_os_cloud.identity.find_domain.assert_called_once_with("admin-domain")

    def test_configuration_1(self):
        config = Configuration(
            True, "cloud-name", "endpoints.yml", False, "admin-domain"
        )

        assert config.dry_run
        assert not config.assign_admin_user


class TestUtils(unittest.TestCase):

    def setUp(self):
        self.patcher = patch("builtins.open")
        self.mock_open = self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.patcher2 = patch("yaml.load")
        self.mock_yaml_load = self.patcher2.start()
        self.addCleanup(self.patcher2.stop)
        self.mock_yaml_load.return_value = MOCK_QUOTA_CLASSES

    def test_get_quotaclass_0(self):
        result = get_quotaclass("classes.yaml", "default")
        self.mock_open.assert_called_once_with("classes.yaml", "r")
        self.mock_yaml_load.assert_called_once()
        assert result == MOCK_QUOTA_CLASSES["default"]

    def test_get_quotaclass_1(self):
        result = get_quotaclass("classes.yaml", "notfound")
        assert result is None

    def test_get_quotaclass_2(self):
        result = get_quotaclass("classes.yaml", "unlimited")
        assert result["compute"]["cores"] == -1
        result["compute"]["cores"] = MOCK_QUOTA_CLASSES["default"]["compute"]["cores"]
        assert result == MOCK_QUOTA_CLASSES["default"]

    def test_check_bool_0(self):
        project = MagicMock()
        project.__contains__.return_value = True
        project.get.return_value = "true"
        assert check_bool(project, "param")
        project.get.return_value = "True"
        assert check_bool(project, "param")
        project.get.return_value = "yes"
        assert check_bool(project, "param")
        project.get.return_value = "Yes"
        assert check_bool(project, "param")
        project.get.return_value = "false"
        assert not check_bool(project, "param")
        project.get.return_value = "False"
        assert not check_bool(project, "param")
        project.get.return_value = "no"
        assert not check_bool(project, "param")
        project.get.return_value = "No"
        assert not check_bool(project, "param")
        project.get.return_value = "Nothing"
        assert not check_bool(project, "param")


class TestBase(CloudTest):

    def setUp(self):
        super().setUp()

        self.patcher3 = patch("builtins.open")
        self.mock_open = self.patcher3.start()
        self.addCleanup(self.patcher3.stop)

        self.patcher4 = patch("yaml.load")
        self.mock_yaml_load = self.patcher4.start()
        self.addCleanup(self.patcher4.stop)
        self.mock_yaml_load.return_value = {
            "default": ["A", "B"],
            "orchestration": ["B", "C"],
        }

        self.config = Configuration(
            False, "cloud-name", "endpoints.yml", True, "admin-domain"
        )

        if not hasattr(self, "select_quota_class"):
            self.select_quota_class = "default"

        self.patcher5 = patch("openstack_project_manager.manage.get_quotaclass")
        self.mock_get_quotaclass = self.patcher5.start()
        self.mock_get_quotaclass.return_value = copy.copy(
            MOCK_QUOTA_CLASSES[self.select_quota_class]
        )
        self.addCleanup(self.patcher5.stop)


class TestCheckQuota(TestBase):

    def test_check_quota_0(self):
        # Network Quotas
        mock_project = MagicMock()
        mock_project.name = "service"
        mock_project.quotamultiplier_network = "5"
        mock_project.quota_router = "6"
        mock_project.__contains__.return_value = True

        self.mock_os_cloud.get_network_quotas.return_value = {
            "floatingip": 5,
            "network": 0,
            "router": 0,
        }

        check_quota(self.config, mock_project, "classes.yaml")

        assert self.mock_os_cloud.set_network_quotas.call_count == 2
        self.mock_os_cloud.set_network_quotas.assert_any_call(ANY, network=5)
        self.mock_os_cloud.set_network_quotas.assert_any_call(ANY, router=6)

    def test_check_quota_1(self):
        # Compute Quotas
        mock_project = MagicMock()
        mock_project.name = "admin"
        mock_project.quotamultiplier_compute = "4"
        mock_project.__contains__.return_value = True

        self.mock_os_cloud.get_compute_quotas.return_value = {
            "cores": 0,
            "injected_file_content_bytes": 0,
            "instances": 4,
        }

        check_quota(self.config, mock_project, "classes.yaml")

        assert self.mock_os_cloud.set_compute_quotas.call_count == 3
        self.mock_os_cloud.set_compute_quotas.assert_any_call(ANY, cores=4)
        self.mock_os_cloud.set_compute_quotas.assert_any_call(
            ANY, injected_file_content_bytes=10240
        )
        self.mock_os_cloud.set_compute_quotas.assert_any_call(ANY, instances=1020)

    def test_check_quota_2(self):
        # Volume Quotas
        mock_project = MagicMock()
        mock_project.name = "other"
        mock_project.quotamultiplier_storage = "3"
        mock_project.__contains__.return_value = True
        mock_project.quotaclass = "other"

        self.mock_os_cloud.get_volume_quotas.return_value = {
            "backup_gigabytes": 0,
            "backups": 0,
            "gigabytes": 0,
        }

        check_quota(self.config, mock_project, "classes.yaml")

        assert self.mock_os_cloud.set_volume_quotas.call_count == 3
        self.mock_os_cloud.set_volume_quotas.assert_any_call(ANY, backup_gigabytes=3)
        self.mock_os_cloud.set_volume_quotas.assert_any_call(ANY, backups=3)
        self.mock_os_cloud.set_volume_quotas.assert_any_call(ANY, gigabytes=3)


class TestCheckBandwidth(TestBase):
    def setUp(self):
        super().setUp()

        self.mock_project = MagicMock()
        self.mock_project.name = "test"
        self.mock_project.id = 9012
        self.mock_domain = MagicMock()
        self.mock_domain.name = "test"
        self.config.os_cloud.get_domain.return_value = self.mock_domain

    def test_update_bandwidth_policy_rule_0(self):
        mock_policy = MagicMock()
        mock_policy.id = 5678
        self.config.os_cloud.list_qos_bandwidth_limit_rules.return_value = []

        update_bandwidth_policy_rule(
            self.config, self.mock_project, mock_policy, "egress", -1, -1
        )

        self.config.os_cloud.delete_qos_bandwidth_limit_rule.assert_not_called()
        self.config.os_cloud.create_qos_bandwidth_limit_rule.assert_not_called()
        self.config.os_cloud.update_qos_bandwidth_limit_rule.assert_not_called()

    def test_update_bandwidth_policy_rule_1(self):
        mock_policy = MagicMock()
        mock_policy.id = 5678
        mock_rule = MagicMock()
        mock_rule.id = 1234
        self.config.os_cloud.list_qos_bandwidth_limit_rules.return_value = [mock_rule]

        update_bandwidth_policy_rule(
            self.config, self.mock_project, mock_policy, "egress", -1, -1
        )

        self.config.os_cloud.delete_qos_bandwidth_limit_rule.assert_called_once_with(
            5678, 1234
        )
        self.config.os_cloud.create_qos_bandwidth_limit_rule.assert_not_called()
        self.config.os_cloud.update_qos_bandwidth_limit_rule.assert_not_called()

    def test_update_bandwidth_policy_rule_2(self):
        mock_policy = MagicMock()
        mock_policy.id = 5678
        self.config.os_cloud.list_qos_bandwidth_limit_rules.return_value = []

        update_bandwidth_policy_rule(
            self.config, self.mock_project, mock_policy, "egress", 100, 200
        )

        self.config.os_cloud.delete_qos_bandwidth_limit_rule.assert_not_called()
        self.config.os_cloud.create_qos_bandwidth_limit_rule.assert_called_once_with(
            5678, max_kbps=100, max_burst_kbps=200, direction="egress"
        )
        self.config.os_cloud.update_qos_bandwidth_limit_rule.assert_not_called()

    def test_update_bandwidth_policy_rule_3(self):
        mock_policy = MagicMock()
        mock_policy.id = 5678
        mock_rule = MagicMock()
        mock_rule.id = 1234
        self.config.os_cloud.list_qos_bandwidth_limit_rules.return_value = [mock_rule]

        update_bandwidth_policy_rule(
            self.config, self.mock_project, mock_policy, "egress", 300, 400
        )

        self.config.os_cloud.delete_qos_bandwidth_limit_rule.assert_not_called()
        self.config.os_cloud.create_qos_bandwidth_limit_rule.assert_not_called()
        self.config.os_cloud.update_qos_bandwidth_limit_rule.assert_called_once_with(
            5678, 1234, max_kbps=300, max_burst_kbps=400
        )

    @patch("openstack_project_manager.manage.update_bandwidth_policy_rule")
    def test_check_bandwidth_limit_0(self, mock_update_bandwidth_policy_rule):
        mock_admin_project = MagicMock()
        mock_admin_project.name = "admin"
        mock_default_domain = MagicMock()
        mock_default_domain.name = "Default"
        self.config.os_cloud.get_domain.return_value = mock_default_domain

        check_bandwidth_limit(self.config, mock_admin_project, {})

        self.config.os_cloud.list_qos_policies.assert_not_called()
        self.config.os_cloud.delete_qos_policy.assert_not_called()
        self.config.os_cloud.create_qos_policy.assert_not_called()
        mock_update_bandwidth_policy_rule.assert_not_called()

    @patch("openstack_project_manager.manage.update_bandwidth_policy_rule")
    def test_check_bandwidth_limit_1(self, mock_update_bandwidth_policy_rule):
        mock_policy = MagicMock()
        mock_policy.id = 5678
        self.config.os_cloud.list_qos_policies.return_value = [mock_policy]
        mock_quota_class = {}

        check_bandwidth_limit(self.config, self.mock_project, mock_quota_class)

        self.config.os_cloud.delete_qos_policy.assert_called_once_with(5678)
        self.config.os_cloud.create_qos_policy.assert_not_called()
        mock_update_bandwidth_policy_rule.assert_not_called()

    @patch("openstack_project_manager.manage.update_bandwidth_policy_rule")
    def test_check_bandwidth_limit_2(self, mock_update_bandwidth_policy_rule):
        self.config.os_cloud.list_qos_policies.return_value = []
        mock_quota_class = {}

        check_bandwidth_limit(self.config, self.mock_project, mock_quota_class)

        self.config.os_cloud.delete_qos_policy.assert_not_called()
        self.config.os_cloud.create_qos_policy.assert_not_called()
        mock_update_bandwidth_policy_rule.assert_not_called()

    @patch("openstack_project_manager.manage.update_bandwidth_policy_rule")
    def test_check_bandwidth_limit_3(self, mock_update_bandwidth_policy_rule):
        self.config.os_cloud.list_qos_policies.return_value = []
        mock_quota_class = {"bandwidth": {"egress": 1000}}

        check_bandwidth_limit(self.config, self.mock_project, mock_quota_class)

        self.config.os_cloud.delete_qos_policy.assert_not_called()
        self.config.os_cloud.create_qos_policy.assert_called_once_with(
            name="bw-limiter", default=True, project_id=9012
        )
        mock_update_bandwidth_policy_rule.assert_any_call(
            self.config, self.mock_project, ANY, "egress", 1000, -1
        )
        mock_update_bandwidth_policy_rule.assert_any_call(
            self.config, self.mock_project, ANY, "ingress", -1, -1
        )

    @patch("openstack_project_manager.manage.update_bandwidth_policy_rule")
    def test_check_bandwidth_limit_4(self, mock_update_bandwidth_policy_rule):
        mock_policy = MagicMock()
        mock_policy.id = 5678
        self.config.os_cloud.list_qos_policies.return_value = [mock_policy]
        mock_quota_class = {
            "bandwidth": {"egress_burst": 1000, "ingress": 2000, "ingress_burst": 3000}
        }

        check_bandwidth_limit(self.config, self.mock_project, mock_quota_class)

        self.config.os_cloud.delete_qos_policy.assert_not_called()
        self.config.os_cloud.create_qos_policy.assert_not_called()
        mock_update_bandwidth_policy_rule.assert_any_call(
            self.config, self.mock_project, mock_policy, "egress", -1, 1000
        )
        mock_update_bandwidth_policy_rule.assert_any_call(
            self.config, self.mock_project, mock_policy, "ingress", 2000, 3000
        )


class TestManageExternalNetworkRbacs(TestBase):

    def setUp(self):
        super().setUp()

        self.mock_domain = MagicMock()
        self.mock_domain.name = "not_default"

    @patch("openstack_project_manager.manage.add_service_network")
    @patch("openstack_project_manager.manage.add_external_network")
    def test_manage_external_network_rbacs_0(
        self, mock_add_external_network, mock_add_service_network
    ):
        mock_project = MagicMock()
        mock_project.__contains__.return_value = True
        mock_project.get.return_value = "True"
        mock_project.public_network = "public_network_name"
        mock_project.service_network = "servic_network_name"

        manage_external_network_rbacs(
            self.config, mock_project, self.mock_domain, "classes.yaml"
        )

        mock_add_external_network.assert_called_once_with(
            self.config, mock_project, "public_network_name"
        )
        mock_add_service_network.assert_called_once_with(
            self.config, mock_project, "servic_network_name"
        )

    @patch("openstack_project_manager.manage.del_service_network")
    @patch("openstack_project_manager.manage.del_external_network")
    def test_manage_external_network_rbacs_1(
        self, mock_del_external_network, mock_del_service_network
    ):
        mock_project = MagicMock()
        mock_project.__contains__.return_value = False
        mock_project.get.return_value = "False"

        manage_external_network_rbacs(
            self.config, mock_project, self.mock_domain, "classes.yaml"
        )

        mock_del_external_network.assert_called_once_with(
            self.config, mock_project, "public"
        )
        mock_del_service_network.assert_called_once_with(
            self.config, mock_project, "not_default-service"
        )


class TestCheckVolumeTypes(TestBase):

    def setUp(self):
        self.select_quota_class = "volume_test"
        super().setUp()

        self.mock_project = MagicMock()
        self.mock_project.id = 1234

        self.mock_domain = MagicMock()
        self.mock_domain.id = 5678
        self.mock_domain.name = "CoMpAnY"

    def mock_volume_type(self, name, location):
        vt = MagicMock()
        vt.name = name
        vt.location.project.id = location
        return vt

    def test_check_volume_types_0(self):
        self.mock_project.__contains__.return_value = True
        vt = self.mock_volume_type("volume_type", 1234)

        self.config.os_cloud.block_storage.types.return_value = [vt]

        check_volume_types(self.config, self.mock_project, MagicMock(), "classes.yaml")

        self.config.os_cloud.block_storage.types.assert_called_once_with(
            name="item1", is_public="False"
        )
        self.config.os_cloud.block_storage.add_type_access.assert_called_with(vt, 1234)

    def test_check_volume_types_1(self):
        self.mock_project.__contains__.return_value = False

        self.config.os_cloud.block_storage.types.return_value = [
            self.mock_volume_type("volume_type", 1234),
            self.mock_volume_type("volume_type_2", 1234),
        ]
        check_volume_types(self.config, self.mock_project, MagicMock(), "classes.yaml")
        self.config.os_cloud.block_storage.add_type_access.assert_not_called()

        self.config.os_cloud.block_storage.types.return_value = []
        check_volume_types(self.config, self.mock_project, MagicMock(), "classes.yaml")
        self.config.os_cloud.block_storage.add_type_access.assert_not_called()

    def test_manage_private_volumetypes_0(self):
        mock_admin_project = MagicMock()
        mock_admin_project.id = 7890
        self.config.os_cloud.get_project.return_value = mock_admin_project

        vt = self.mock_volume_type("COMPANY-private-volume-type", 7890)

        self.config.os_cloud.block_storage.types.return_value = [
            self.mock_volume_type("volume_type_1", 7890),
            vt,
            self.mock_volume_type("COMPANY-do-not-use", 5678),
            self.mock_volume_type("company-already-using", 7890),
            self.mock_volume_type("volume_type_2", 1234),
        ]

        self.config.os_cloud.block_storage.get_type.side_effect = lambda t: t

        def mock_get_type_access(volume_type):
            accessIds = []
            if volume_type.name in [
                "COMPANY-private-volume-type",
                "company-already-using",
                "volume_type_1",
            ]:
                accessIds.append(7890)
            if volume_type.name in ["company-already-using"]:
                accessIds.append(1234)

            ret = []
            for i in accessIds:
                ret.append({"project_id": i, "volume_type_id": i + 1000})

            return ret

        self.config.os_cloud.block_storage.get_type_access.side_effect = (
            mock_get_type_access
        )

        manage_private_volumetypes(self.config, self.mock_project, self.mock_domain)

        self.config.os_cloud.block_storage.add_type_access.assert_called_once_with(
            vt, 1234
        )

    def test_manage_private_volumetypes_1(self):
        mock_admin_project = MagicMock()
        mock_admin_project.id = 7890
        self.config.os_cloud.get_project.return_value = mock_admin_project

        manage_private_volumetypes(self.config, mock_admin_project, self.mock_domain)

        self.config.os_cloud.block_storage.types.assert_not_called()


class TestCreateNetworkResources(TestBase):

    @patch("openstack_project_manager.manage.create_network_with_router")
    def test_create_network_resources_0(self, mock_create_network_with_router):
        mock_project = MagicMock()
        mock_project.name = "project_name"
        mock_project.__contains__.return_value = True
        mock_project.quotamultiplier = "1"
        mock_project.quotamultiplier_network = "2"

        def mock_get(name: str):
            return name != "is_service_project"

        mock_project.get.side_effect = mock_get
        mock_project.public_network = "public_network_name"
        mock_project.service_network = "service_network_name"

        mock_domain = MagicMock()
        mock_domain.name = "not_default"

        create_network_resources(self.config, mock_project, mock_domain)

        mock_create_network_with_router.assert_any_call(
            self.config,
            mock_project,
            "net-to-public_network_name-project_name",
            "subnet-to-public_network_name-project_name",
            "router-to-public_network_name-project_name",
            "public_network_name",
            "nova",
        )

        mock_create_network_with_router.assert_any_call(
            self.config,
            mock_project,
            "net-to-service_network_name-project_name",
            "subnet-to-service_network_name-project_name",
            "router-to-service_network_name-project_name",
            "service_network_name",
            "nova",
        )

    @patch("openstack_project_manager.manage.create_service_network")
    @patch("openstack_project_manager.manage.create_network_with_router")
    def test_create_network_resources_1(
        self, mock_create_network_with_router, mock_create_service_network
    ):
        mock_project = MagicMock()
        mock_project.name = "project_name"

        def mock_get(name: str):
            return (
                name == "has_service_network"
                or name == "has_public_network"
                or name == "is_service_project"
            )

        mock_project.__contains__.side_effect = mock_get
        mock_project.get.side_effect = mock_get
        mock_project.service_network_cidr = "cdir"

        mock_domain = MagicMock()
        mock_domain.name = "not_default"

        create_network_resources(self.config, mock_project, mock_domain)

        mock_create_network_with_router.assert_not_called()
        mock_create_service_network.assert_called_once_with(
            self.config,
            mock_project,
            "not_default-service",
            "subnet-not_default-service",
            "nova",
            "cdir",
        )


class TestModifyNetwork(TestBase):

    def setUp(self):
        super().setUp()

        self.mock_project = MagicMock()
        self.mock_project.id = 1234

        self.mock_network = MagicMock()
        self.mock_network.id = 5678
        self.config.os_cloud.get_network.return_value = self.mock_network

    def test_add_service_network(self):
        self.mock_project.__contains__.return_value = True
        self.mock_project.service_network_type = "network_type_name"

        add_service_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_network_type_name",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.create_rbac_policy.assert_called_once_with(
            {
                "rbac_policy": {
                    "target_tenant": 1234,
                    "action": "access_as_network_type_name",
                    "object_type": "network",
                    "object_id": 5678,
                }
            }
        )

    def test_del_service_network(self):
        del_service_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_shared",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.delete_rbac_policy.assert_not_called()

        self.config.os_neutron.list_rbac_policies.return_value = {
            "rbac_policies": [{"id": 9012}]
        }
        del_service_network(self.config, self.mock_project, "network_name")
        self.config.os_neutron.delete_rbac_policy.assert_called_once_with(9012)

    def test_add_external_network(self):
        add_external_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_external",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.create_rbac_policy.assert_called_once_with(
            {
                "rbac_policy": {
                    "target_tenant": 1234,
                    "action": "access_as_external",
                    "object_type": "network",
                    "object_id": 5678,
                }
            }
        )

    def test_del_external_network(self):
        del_external_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_external",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.delete_rbac_policy.assert_not_called()

        self.config.os_neutron.list_rbac_policies.return_value = {
            "rbac_policies": [{"id": 9012}]
        }
        del_external_network(self.config, self.mock_project, "network_name")
        self.config.os_neutron.delete_rbac_policy.assert_called_once_with(9012)


class TestCreateNetwork(TestBase):

    def setUp(self):
        super().setUp()
        self.mock_project = MagicMock()
        self.mock_project.id = 9999
        self.mock_project.domain_id = 1234
        self.mock_project.name = "project_name"

        mock_domain = MagicMock()
        mock_domain.name = "domain_name"
        self.config.os_cloud.get_domain.return_value = mock_domain

        self.mock_service_project = MagicMock()
        self.mock_service_project.id = 5678
        self.config.os_cloud.get_project.return_value = self.mock_service_project

        self.mock_network = MagicMock()
        self.mock_network.id = 9012
        self.config.os_cloud.create_network.return_value = self.mock_network

        self.mock_subnet = MagicMock()
        self.mock_subnet.id = 1111
        self.config.os_cloud.create_subnet.return_value = self.mock_subnet

    @patch("openstack_project_manager.manage.add_service_network")
    def test_create_service_network_0(self, mock_add_service_network):
        self.config.os_cloud.get_network.return_value = None
        self.config.os_cloud.get_subnet.return_value = None

        create_service_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
            "subnet_cidr",
        )

        self.config.os_cloud.create_network.assert_called_once_with(
            "network_name",
            project_id=5678,
            availability_zone_hints=["availability_zone"],
        )
        mock_add_service_network.assert_called_once_with(
            self.config, self.mock_service_project, "network_name"
        )
        self.config.os_cloud.create_subnet.assert_called_once_with(
            9012,
            tenant_id=5678,
            subnet_name="subnet_name",
            cidr="subnet_cidr",
            enable_dhcp=True,
        )

    @patch("openstack_project_manager.manage.add_service_network")
    def test_create_service_network_1(self, mock_add_service_network):
        self.config.os_cloud.get_network.return_value = self.mock_network
        self.config.os_cloud.get_subnet.return_value = None

        create_service_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
            None,
        )

        self.config.os_cloud.create_network.assert_not_called()
        mock_add_service_network.assert_not_called()
        self.config.os_cloud.create_subnet.assert_called_once_with(
            9012,
            tenant_id=5678,
            subnet_name="subnet_name",
            use_default_subnetpool=True,
            enable_dhcp=True,
        )

    @patch("openstack_project_manager.manage.add_service_network")
    def test_create_service_network_2(self, mock_add_service_network):
        self.config.os_cloud.get_subnet.return_value = self.mock_subnet

        create_service_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
            None,
        )

        self.config.os_cloud.create_subnet.assert_not_called()

    def test_create_network_0(self):
        self.config.os_cloud.get_network.return_value = None
        self.config.os_cloud.get_subnet.return_value = None

        attach, subnet = create_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        assert attach
        assert subnet is self.mock_subnet

        self.config.os_cloud.create_network.assert_called_once_with(
            "network_name",
            project_id=9999,
            availability_zone_hints=["availability_zone"],
        )
        self.config.os_cloud.create_subnet.assert_called_once_with(
            9012,
            tenant_id=9999,
            subnet_name="subnet_name",
            use_default_subnetpool=True,
            enable_dhcp=True,
        )

    def test_create_network_1(self):
        self.config.os_cloud.get_network.return_value = self.mock_network
        self.config.os_cloud.get_subnet.return_value = self.mock_subnet

        attach, subnet = create_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        assert not attach
        assert subnet is self.mock_subnet

        self.config.os_cloud.create_network.assert_not_called()
        self.config.os_cloud.create_subnet.assert_not_called()

    @patch("openstack_project_manager.manage.create_network")
    def test_create_network_with_router_0(self, mock_create_network):
        mock_router = MagicMock()
        self.config.os_cloud.create_router.return_value = mock_router
        self.config.os_cloud.get_router.return_value = None
        self.config.os_cloud.get_network.return_value = self.mock_network
        mock_create_network.return_value = (False, self.mock_subnet)

        create_network_with_router(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "router_name",
            "public_net_name",
            "availability_zone",
        )

        self.config.os_cloud.create_router.assert_called_once_with(
            name="router_name",
            ext_gateway_net_id=9012,
            enable_snat=True,
            project_id=9999,
            availability_zone_hints=["availability_zone"],
        )

        mock_create_network.assert_called_once_with(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        self.config.os_cloud.add_router_interface.assert_called_once_with(
            mock_router, subnet_id=1111
        )

    @patch("openstack_project_manager.manage.create_network")
    def test_create_network_with_router_1(self, mock_create_network):
        mock_router = MagicMock()
        self.config.os_cloud.get_router.return_value = mock_router
        mock_create_network.return_value = (True, self.mock_subnet)

        create_network_with_router(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "router_name",
            "public_net_name",
            "availability_zone",
        )

        self.config.os_cloud.create_router.assert_not_called()

        mock_create_network.assert_called_once_with(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        self.config.os_cloud.add_router_interface.assert_called_once_with(
            mock_router, subnet_id=1111
        )

    @patch("openstack_project_manager.manage.create_network")
    def test_create_network_with_router_2(self, mock_create_network):
        mock_router = MagicMock()
        self.config.os_cloud.get_router.return_value = mock_router
        mock_create_network.return_value = (False, self.mock_subnet)

        create_network_with_router(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "router_name",
            "public_net_name",
            "availability_zone",
        )

        self.config.os_cloud.create_router.assert_not_called()

        mock_create_network.assert_called_once_with(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        self.config.os_cloud.add_router_interface.assert_not_called()


class TestPermissions(TestBase):

    def setUp(self):
        super().setUp()

        self.mock_project = MagicMock()
        self.mock_project.id = 1234
        self.mock_project.__contains__.return_value = True
        self.mock_project.get.return_value = "True"
        self.mock_project.name = "domainname-username"
        self.mock_project.endpoints = "default,orchestration"

        self.mock_domain = MagicMock()
        self.mock_domain.id = 5678
        self.mock_domain.name = "domainname"

        self.mock_user = MagicMock()
        self.mock_user.id = 9012
        self.config.os_cloud.identity.find_user.return_value = self.mock_user

    def test_check_homeproject_permissions_0(self):
        def mock_find_user(name, domain_id):
            if name == "username":
                return self.mock_user
            return None

        self.config.os_cloud.identity.find_user.side_effect = mock_find_user

        check_homeproject_permissions(self.config, self.mock_project, self.mock_domain)

        for rolename in self.config.CACHE_ROLES:
            self.config.os_cloud.identity.assign_project_role_to_user.assert_any_call(
                1234, 9012, self.config.CACHE_ROLES[rolename].id
            )

    def test_check_homeproject_permissions_1(self):
        def mock_find_user(name, domain_id):
            if name == "username":
                return self.mock_user
            return None

        self.config.os_cloud.identity.find_user.side_effect = mock_find_user

        self.mock_project.name = "domainname-username-cache1"

        check_homeproject_permissions(self.config, self.mock_project, self.mock_domain)

        for rolename in self.config.CACHE_ROLES:
            self.config.os_cloud.identity.assign_project_role_to_user.assert_any_call(
                1234, 9012, self.config.CACHE_ROLES[rolename].id
            )

    def test_assign_admin_user(self):
        assert "domainname-admin" not in self.config.CACHE_ADMIN_USERS

        assign_admin_user(self.config, self.mock_project, self.mock_domain)

        assert "domainname-admin" in self.config.CACHE_ADMIN_USERS

        self.config.os_cloud.identity.assign_project_role_to_user.assert_called_once_with(
            1234, 9012, 0
        )

    def test_check_endpoints(self):
        A = MagicMock()
        A.name = "A-internal"
        A.id = 1
        B = MagicMock()
        B.name = "B-public"
        B.id = 2
        C = MagicMock()
        C.name = "C-internal"
        C.id = 3
        D = MagicMock()
        D.name = "D-public"
        D.id = 4
        self.config.os_keystone.endpoint_groups.list.return_value = [A, B, C]
        self.config.os_keystone.endpoint_filter.list_endpoint_groups_for_project.return_value = [
            B,
            C,
            D,
        ]

        check_endpoints(self.config, self.mock_project)

        self.config.os_keystone.endpoint_filter.add_endpoint_group_to_project.assert_called_once_with(
            endpoint_group=1, project=1234
        )


class TestImages(TestBase):

    def setUp(self):
        super().setUp()
        self.mock_domain = MagicMock()
        self.mock_domain.id = 3333

        self.mock_project = MagicMock()
        self.mock_project.id = 1234
        self.config.os_cloud.get_project.return_value = self.mock_project

        self.mock_image = MagicMock()
        self.mock_image.id = 5678
        self.mock_image.name = "Ubuntu"
        self.mock_image.size = 5 * 1024 * 1024 * 1024
        self.mock_image.min_disk = 5

        self.mock_image2 = MagicMock()
        self.mock_image2.id = 9999
        self.mock_image2.name = "CentOS"
        self.mock_image2.size = 20 * 1024 * 1024 * 1024
        self.mock_image2.min_disk = 20

        self.config.os_cloud.image.images.return_value = [
            self.mock_image,
            self.mock_image2,
        ]

        def mock_find_image(name_or_id=None):
            if name_or_id == "Ubuntu" or name_or_id == "5678":
                return self.mock_image
            elif name_or_id == "CentOS" or name_or_id == "9999":
                return self.mock_image2
            return None

        self.config.os_cloud.image.find_image.side_effect = mock_find_image

        self.mock_member = MagicMock()
        self.mock_member.id = 9012
        self.mock_member.status = "unaccepted"

        def mock_update_member(member, image_id, status):
            self.mock_member = status

        self.config.os_cloud.image.update_member.side_effect = mock_update_member

    def test_share_image_with_project(self):
        self.config.os_cloud.image.find_member.return_value = None
        self.config.os_cloud.image.add_member.return_value = self.mock_member

        share_image_with_project(self.config, self.mock_image, self.mock_project)

        self.config.os_cloud.image.add_member.assert_called_once_with(
            5678, member_id=1234
        )
        assert self.mock_member == "accepted"

    @patch("openstack_project_manager.manage.share_image_with_project")
    def test_share_images(self, mock_share_image_with_project):
        share_images(self.config, self.mock_project, self.mock_image)

        assert mock_share_image_with_project.call_count == 2

        mock_share_image_with_project.assert_any_call(
            self.config, self.mock_image, self.mock_project
        )
        mock_share_image_with_project.assert_any_call(
            self.config, self.mock_image2, self.mock_project
        )

    def test_cache_images(self):
        mock_volume1 = MagicMock()
        mock_volume1.name = "cache-5678"
        mock_volume2 = MagicMock()
        mock_volume2.name = "cache-7777"
        self.config.os_cloud.volume.volumes.return_value = [mock_volume1, mock_volume2]

        def mock_find_volume(name_or_id=None):
            if name_or_id == "cache-5678":
                return mock_volume1
            elif name_or_id == "cache-7777":
                return mock_volume2
            return None

        self.config.os_cloud.volume.find_volume.side_effect = mock_find_volume

        cache_images(self.config, self.mock_domain)

        self.config.os_cloud.volume.delete_volume.assert_called_once_with(mock_volume2)
        self.config.os_cloud.volume.create_volume.assert_called_once_with(
            name="cache-9999", size=20, imageRef=9999
        )


class TestProcessProject(TestBase):

    def setUp(self):
        super().setUp()

        self.mock_project = MagicMock()
        self.mock_project.id = 1234
        self.mock_project.name = "project_name"
        self.mock_project.domain_id = 5678
        self.mock_project.quotaclass = "default"
        self.mock_project.__contains__.return_value = False

        self.mock_domain = MagicMock()
        self.config.os_cloud.get_domain.return_value = self.mock_domain

    @patch("openstack_project_manager.manage.manage_private_volumetypes")
    @patch("openstack_project_manager.manage.check_volume_types")
    @patch("openstack_project_manager.manage.create_network_resources")
    @patch("openstack_project_manager.manage.share_images")
    @patch("openstack_project_manager.manage.manage_external_network_rbacs")
    @patch("openstack_project_manager.manage.assign_admin_user")
    @patch("openstack_project_manager.manage.check_homeproject_permissions")
    @patch("openstack_project_manager.manage.check_endpoints")
    @patch("openstack_project_manager.manage.check_quota")
    def test_process_project_0(
        self,
        mock_check_quota,
        mock_check_endpoints,
        mock_check_homeproject_permissions,
        mock_assign_admin_user,
        mock_manage_external_network_rbacs,
        mock_share_images,
        mock_create_network_resources,
        mock_check_volume_types,
        mock_manage_private_volumetypes,
    ):
        process_project(
            self.config, self.mock_project, "classes.yaml", True, True, True
        )

        mock_check_quota.assert_called_once_with(
            self.config, self.mock_project, "classes.yaml"
        )
        mock_check_endpoints.assert_called_once_with(self.config, self.mock_project)
        mock_check_homeproject_permissions.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain
        )
        mock_assign_admin_user.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain
        )
        mock_manage_external_network_rbacs.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain, "classes.yaml"
        )
        mock_share_images.assert_not_called()
        mock_create_network_resources.assert_not_called()
        mock_check_volume_types.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain, "classes.yaml"
        )
        mock_manage_private_volumetypes.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain
        )

    @patch("openstack_project_manager.manage.manage_private_volumetypes")
    @patch("openstack_project_manager.manage.check_volume_types")
    @patch("openstack_project_manager.manage.create_network_resources")
    @patch("openstack_project_manager.manage.share_images")
    @patch("openstack_project_manager.manage.manage_external_network_rbacs")
    @patch("openstack_project_manager.manage.assign_admin_user")
    @patch("openstack_project_manager.manage.check_homeproject_permissions")
    @patch("openstack_project_manager.manage.check_endpoints")
    @patch("openstack_project_manager.manage.check_quota")
    def test_process_project_1(
        self,
        mock_check_quota,
        mock_check_endpoints,
        mock_check_homeproject_permissions,
        mock_assign_admin_user,
        mock_manage_external_network_rbacs,
        mock_share_images,
        mock_create_network_resources,
        mock_check_volume_types,
        mock_manage_private_volumetypes,
    ):
        self.config.assign_admin_user = False

        def mock_contains(name):
            return name != "unmanaged"

        self.mock_project.__contains__.return_value = None
        self.mock_project.__contains__.side_effect = mock_contains
        self.mock_project.get.return_value = "True"

        process_project(
            self.config, self.mock_project, "classes.yaml", False, False, False
        )

        mock_check_quota.assert_called_once_with(
            self.config, self.mock_project, "classes.yaml"
        )
        mock_check_endpoints.assert_not_called()
        mock_check_homeproject_permissions.assert_not_called()
        mock_assign_admin_user.assert_not_called()
        mock_manage_external_network_rbacs.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain, "classes.yaml"
        )
        mock_share_images.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain
        )
        mock_create_network_resources.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain
        )
        mock_check_volume_types.assert_called_once_with(
            self.config, self.mock_project, self.mock_domain, "classes.yaml"
        )
        mock_manage_private_volumetypes.assert_not_called()

    @patch("openstack_project_manager.manage.manage_private_volumetypes")
    @patch("openstack_project_manager.manage.check_volume_types")
    @patch("openstack_project_manager.manage.create_network_resources")
    @patch("openstack_project_manager.manage.share_images")
    @patch("openstack_project_manager.manage.manage_external_network_rbacs")
    @patch("openstack_project_manager.manage.assign_admin_user")
    @patch("openstack_project_manager.manage.check_homeproject_permissions")
    @patch("openstack_project_manager.manage.check_endpoints")
    @patch("openstack_project_manager.manage.check_quota")
    def test_process_project_2(
        self,
        mock_check_quota,
        mock_check_endpoints,
        mock_check_homeproject_permissions,
        mock_assign_admin_user,
        mock_manage_external_network_rbacs,
        mock_share_images,
        mock_create_network_resources,
        mock_check_volume_types,
        mock_manage_private_volumetypes,
    ):
        def mock_contains(name):
            return name == "unmanaged"

        self.mock_project.__contains__.return_value = None
        self.mock_project.__contains__.side_effect = mock_contains
        self.mock_project.get.return_value = "True"

        process_project(
            self.config, self.mock_project, "classes.yaml", True, True, True
        )

        mock_check_quota.assert_not_called()
        mock_check_endpoints.assert_not_called()
        mock_check_homeproject_permissions.assert_not_called()
        mock_assign_admin_user.assert_not_called()
        mock_manage_external_network_rbacs.assert_not_called()
        mock_share_images.assert_not_called()
        mock_create_network_resources.assert_not_called()
        mock_check_volume_types.assert_not_called()
        mock_manage_private_volumetypes.assert_not_called()

    @patch("openstack_project_manager.manage.check_quota")
    @patch("openstack_project_manager.manage.add_external_network")
    def test_handle_unmanaged_project_0(
        self, mock_add_external_network, mock_check_quota
    ):
        self.mock_project.name = "service"

        handle_unmanaged_project(self.config, self.mock_project, "classes.yaml")

        mock_add_external_network.assert_called_once_with(
            self.config, self.mock_project, "public"
        )
        mock_check_quota.assert_called_once_with(
            self.config, self.mock_project, "classes.yaml"
        )

    @patch("openstack_project_manager.manage.check_quota")
    @patch("openstack_project_manager.manage.add_external_network")
    def test_handle_unmanaged_project_1(
        self, mock_add_external_network, mock_check_quota
    ):
        self.mock_project.name = "not-service"

        handle_unmanaged_project(self.config, self.mock_project, "classes.yaml")

        mock_add_external_network.assert_not_called()
        mock_check_quota.assert_called_once_with(
            self.config, self.mock_project, "classes.yaml"
        )

    @patch("openstack_project_manager.manage.add_external_network")
    def test_handle_unmanaged_project_2(self, mock_add_external_network):
        self.mock_project.name = "service"
        self.mock_project.__contains__.return_value = True
        self.mock_project.public_network = "public_net_name"

        handle_unmanaged_project(self.config, self.mock_project, "classes.yaml")

        mock_add_external_network.assert_called_once_with(
            self.config, self.mock_project, "public_net_name"
        )


class TestCLI(CloudTest):

    def setUp(self):
        super().setUp()
        self.runner = CliRunner()

        self.mock_domain1 = MagicMock()
        self.mock_domain1.name = "domain_1"
        self.mock_domain1.id = "default"

        self.mock_domain2 = MagicMock()
        self.mock_domain2.name = "domain_2"
        self.mock_domain2.id = "domain2"

        self.mock_project1 = MagicMock()
        self.mock_project1.domain_id = "domain2"
        self.mock_project1.name = "project_1"
        self.mock_project1.id = 9012

        self.mock_project2 = MagicMock()
        self.mock_project2.domain_id = "default"
        self.mock_project2.name = "service"
        self.mock_project2.id = 3456

        def mock_list_projects(domain_id=None):
            if domain_id == "default":
                return [self.mock_project2]
            elif domain_id == "domain2":
                return [self.mock_project1]
            return None

        self.mock_os_cloud.list_projects.side_effect = mock_list_projects

        self.patcher_cli_1 = patch(
            "openstack_project_manager.manage.handle_unmanaged_project"
        )
        self.mock_handle_unmanaged_project = self.patcher_cli_1.start()
        self.addCleanup(self.patcher_cli_1.stop)

        self.patcher_cli_2 = patch("openstack_project_manager.manage.process_project")
        self.mock_process_project = self.patcher_cli_2.start()
        self.addCleanup(self.patcher_cli_2.stop)

        self.patcher_cli_3 = patch("openstack_project_manager.manage.cache_images")
        self.mock_cache_images = self.patcher_cli_3.start()
        self.addCleanup(self.patcher_cli_3.stop)

    def assume_project_1(self, assume_cache_images):
        self.mock_handle_unmanaged_project.assert_not_called()
        self.mock_process_project.assert_called_once_with(
            ANY, self.mock_project1, ANY, False, False, True
        )
        if not assume_cache_images:
            self.mock_cache_images.assert_not_called()
        else:
            self.mock_cache_images.assert_any_call(ANY, self.mock_domain2)

    def assume_project_2(self, assume_cache_images):
        self.mock_handle_unmanaged_project.assert_called_once_with(
            ANY, self.mock_project2, ANY
        )
        self.mock_process_project.assert_not_called()
        if not assume_cache_images:
            self.mock_cache_images.assert_not_called()
        else:
            self.mock_cache_images.assert_any_call(ANY, self.mock_domain1)

    def test_cli_0(self):
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))
        self.mock_connect.assert_not_called()

    def test_cli_1(self):
        self.mock_os_cloud.list_domains.return_value = [
            self.mock_domain1,
            self.mock_domain2,
        ]

        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_handle_unmanaged_project.assert_called_once_with(
            ANY, self.mock_project2, ANY
        )
        self.mock_process_project.assert_called_once_with(
            ANY, self.mock_project1, ANY, False, False, True
        )
        self.mock_cache_images.assert_any_call(ANY, self.mock_domain1)
        self.mock_cache_images.assert_any_call(ANY, self.mock_domain2)

    def test_cli_2(self):
        self.mock_os_cloud.get_project.return_value = self.mock_project2

        result = self.runner.invoke(app, ["--name=service"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.assume_project_2(False)

    def test_cli_3(self):
        self.mock_os_cloud.get_project.return_value = self.mock_project1

        result = self.runner.invoke(app, ["--name=project_1"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.assume_project_1(False)

    def test_cli_4(self):
        self.mock_os_cloud.get_domain.return_value = self.mock_domain1
        self.mock_os_cloud.get_project.return_value = self.mock_project2

        result = self.runner.invoke(app, ["--domain=domain_1", "--name=service"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.assume_project_2(False)

    def test_cli_5(self):
        self.mock_os_cloud.get_domain.return_value = self.mock_domain2
        self.mock_os_cloud.get_project.return_value = self.mock_project1

        result = self.runner.invoke(app, ["--domain=domain_2", "--name=project_1"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.assume_project_1(False)

    def test_cli_6(self):
        self.mock_os_cloud.get_domain.return_value = self.mock_domain1

        result = self.runner.invoke(app, ["--domain=domain_1"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.assume_project_2(True)

    def test_cli_7(self):
        self.mock_os_cloud.get_domain.return_value = self.mock_domain2

        result = self.runner.invoke(app, ["--domain=domain_2"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.assume_project_1(True)

    def test_cli_8(self):
        self.mock_os_cloud.get_domain.return_value = self.mock_domain2

        result = self.runner.invoke(
            app,
            [
                "--domain=domain_2",
                "--manage-endpoints",
                "--manage-homeprojects",
                "--nomanage-privatevolumetypes",
                "--classes=other.yaml",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_process_project.assert_called_once_with(
            ANY, self.mock_project1, "other.yaml", True, True, False
        )

    def test_cli_9(self):
        self.patcher_cli_1.stop()
        self.patcher_cli_2.stop()
        self.patcher_cli_3.stop()
        self.mock_os_cloud.list_domains.return_value = [
            self.mock_domain1,
            self.mock_domain2,
        ]

        result = self.runner.invoke(app, ["--dry-run"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.set_network_quotas.assert_not_called()
        self.mock_os_cloud.set_compute_quotas.assert_not_called()
        self.mock_os_cloud.set_volume_quotas.assert_not_called()
        self.mock_os_neutron.create_rbac_policy.assert_not_called()
        self.mock_os_neutron.delete_rbac_policy.assert_not_called()
        self.mock_os_cloud.create_network.assert_not_called()
        self.mock_os_cloud.create_subnet.assert_not_called()
        self.mock_os_cloud.create_router.assert_not_called()
        self.mock_os_cloud.add_router_interface.assert_not_called()
        self.mock_os_keystone.endpoint_filter.add_endpoint_group_to_project.assert_not_called()


if __name__ == "__main__":
    unittest.main()
