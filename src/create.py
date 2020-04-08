import random
import string
import sys

from oslo_config import cfg
import os_client_config
import openstack

PROJECT_NAME = 'openstack-project-manager'
CONF = cfg.CONF
opts = [
  cfg.BoolOpt('create_user', help='Create user', default=True),
  cfg.BoolOpt('random', help='Generate random names', default=False),
  cfg.IntOpt('quota_router', help='Quota router', default=None),
  cfg.IntOpt('quota_multiplier', help='Quota multiplier', default='1'),
  cfg.IntOpt('quota_multiplier_compute', help='Quota multiplier compute', default=None),
  cfg.IntOpt('quota_multiplier_network', help='Quota multiplier network', default=None),
  cfg.IntOpt('quota_multiplier_storage', help='Quota multiplier storage', default=None),
  cfg.StrOpt('cloud', help='Managed cloud', default='service'),
  cfg.StrOpt('domain', help='Domain', default='orange'),
  cfg.StrOpt('name', help='Projectname', default='test-123'),
  cfg.StrOpt('owner', help='Owner of the project', default='operations@betacloud.de'),
  cfg.StrOpt('password', help='Password', default=None),
  cfg.StrOpt('public_network', help='Public network', default='external'),
  cfg.StrOpt('quota_class', help='Quota class', default='basic')
]
CONF.register_cli_opts(opts)

CONF(sys.argv[1:], project=PROJECT_NAME)
conn = openstack.connect(cloud=CONF.cloud)

if CONF.random:
    name = "test-" + "".join(random.choice(string.ascii_letters) for x in range(8)).lower()
else:
    name = CONF.name

if not CONF.password:
    password = "".join(random.choice(string.ascii_letters + string.digits) for x in range(16))
else:
    password = CONF.password

# FIXME(berendt): use get_domain
domain = conn.identity.find_domain(CONF.domain)

# FIXME(berendt): use get_project
project = conn.identity.find_project(name, domain_id=domain.id)
if not project:
    project = conn.create_project(name=name, domain_id=domain.id)

# FIXME(berendt): use openstacksdk
keystone = os_client_config.make_client('identity', cloud=CONF.cloud)

keystone.projects.update(project=project.id, quotaclass=CONF.quota_class)
keystone.projects.update(project=project.id, quotamultiplier=CONF.quota_multiplier)
if CONF.quota_multiplier_compute:
    keystone.projects.update(project=project.id, quotamultiplier_compute=CONF.quota_multiplier_compute)
if CONF.quota_multiplier_network:
    keystone.projects.update(project=project.id, quotamultiplier_network=CONF.quota_multiplier_network)
if CONF.quota_multiplier_storage:
    keystone.projects.update(project=project.id, quotamultiplier_storage=CONF.quota_multiplier_storage)
if CONF.quota_router:
    keystone.projects.update(project=project.id, quota_router=CONF.quota_router)

keystone.projects.update(project=project.id, has_domain_network="False")
keystone.projects.update(project=project.id, has_shared_router="False")
keystone.projects.update(project=project.id, has_public_network="False")
keystone.projects.update(project=project.id, show_public_network="True")
keystone.projects.update(project=project.id, public_network=CONF.public_network)

keystone.projects.update(project=project.id, owner=CONF.owner)

if CONF.create_user:
    user = conn.identity.find_user(name, domain_id=domain.id)
    if not user:
        user = conn.create_user(name=name, password=password, default_project=project, domain_id=domain.id, email=CONF.owner)
    else:
        conn.update_user(user, password=password)

    # FIXME(berendt): check existing assignments
    conn.grant_role("_member_", user=user.id, project=project.id, domain=domain.id)
    conn.grant_role("heat_stack_owner", user=user.id, project=project.id, domain=domain.id)

print("domain: %s (%s)" % (CONF.domain, domain.id))
print("project: %s (%s)" % (name, project.id))

if CONF.create_user:
    print("user: %s (%s)" % (name, user.id))
    print("password: " + password)
