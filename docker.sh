#!/bin/bash
set -e

if ! command -v docker &>/dev/null; then
	dnf remove -y docker docker-{client,client-latest,common,latest,latest-logrotate,logrotate,selinux,engine-selinux,engine} || true
	rm -rf /var/lib/docker
	dnf config-manager addrepo --from-repofile https://download.docker.com/linux/fedora/docker-ce.repo
	dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
	systemctl enable --now docker
	docker run hello-world
	usermod -aG docker vagrant
fi

cd /vagrant && docker compose up -d


