#!/usr/bin/env bash

domain="$1"
project="$2"
user="$3"

openstack --os-cloud service role add --project-domain "$domain" --project "$project" --user-domain "$domain" --user "$user" _member_
openstack --os-cloud service role add --project-domain "$domain" --project "$project" --user-domain "$domain" --user "$user" heat_stack_owner
openstack --os-cloud service role add --project-domain "$domain" --project "$project" --user-domain "$domain" --user "$user" load-balancer_member
