#!/usr/bin/env bash
# Configurazione NVIDIA Container Toolkit per Podman (openSUSE Tumbleweed)
# Eseguire con: sudo bash setup-podman-gpu.sh

set -euo pipefail
echo "=== Aggiunta repository NVIDIA Container Toolkit ==="
zypper --non-interactive addrepo --refresh \
  https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo

echo "=== Installazione nvidia-container-toolkit ==="
zypper --non-interactive install nvidia-container-toolkit

echo "=== Configurazione crun per Podman ==="
nvidia-ctk runtime configure --runtime=crun

echo "=== Generazione configurazione CDI ==="
nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

echo "=== Verifica CDI ==="
nvidia-ctk cdi list

echo ""
echo "=== Fatto! Riavviare Podman con: ==="
echo "    sudo systemctl restart podman"
echo ""
echo "=== Poi avviare lo stack con: ==="
echo "    podman-compose up -d"
