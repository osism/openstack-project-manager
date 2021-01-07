#!/usr/bin/env bash

domain="$1"
user="$2"
email="$3"

openstack --os-cloud service user create --domain "$domain" --email "$email" --password-prompt "$user"
