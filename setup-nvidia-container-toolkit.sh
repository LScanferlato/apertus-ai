#!/usr/bin/env bash
# Configurazione NVIDIA Container Toolkit per Docker o Podman.
# Supporta: Ubuntu (apt) e openSUSE (zypper)
# Eseguire con: sudo bash setup-nvidia-container-toolkit.sh

set -euo pipefail

# --- Rilevamento OS ---
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_VERSION="${VERSION_ID:-}"
else
    echo "ERRORE: impossibile rilevare il sistema operativo."
    exit 1
fi

echo "=== OS rilevato: $ID $VERSION_ID ==="

# --- Repository NVIDIA + installazione ---
case "$OS_ID" in
    ubuntu|debian)
        echo "=== Aggiunta repository NVIDIA Container Toolkit ==="
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
            gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        apt-get update -qq
        echo "=== Installazione nvidia-container-toolkit ==="
        apt-get install -y -qq nvidia-container-toolkit
        ;;
    opensuse-tumbleweed|opensuse-leap|suse)
        echo "=== Aggiunta repository NVIDIA Container Toolkit ==="
        zypper --non-interactive addrepo --refresh \
            https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo
        echo "=== Installazione nvidia-container-toolkit ==="
        zypper --non-interactive install nvidia-container-toolkit
        ;;
    fedora|rhel|centos)
        echo "=== Aggiunta repository NVIDIA Container Toolkit ==="
        dnf config-manager --add-repo \
            https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo
        echo "=== Installazione nvidia-container-toolkit ==="
        dnf install -y nvidia-container-toolkit
        ;;
    *)
        echo "ERRORE: OS non supportato ($OS_ID). Installare nvidia-container-toolkit manualmente."
        echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        exit 1
        ;;
esac

# --- Configurazione runtime rilevato ---
if command -v podman &>/dev/null; then
    echo "=== Podman rilevato: generazione configurazione CDI ==="
    nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
    nvidia-ctk cdi list
    echo "  Podman: le GPU sono disponibili via '--device nvidia.com/gpu=all'"
elif command -v docker &>/dev/null; then
    echo "=== Docker rilevato: configurazione runtime nvidia ==="
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    echo "  Docker: runtime nvidia configurato"
else
    echo "AVVISO: né Docker né Podman rilevati. Il toolkit NVIDIA è installato ma va configurato manualmente."
fi

echo ""
echo "=== ✅ Fatto! NVIDIA Container Toolkit configurato per $OS_ID ==="
echo ""
echo "Per avviare lo stack:"
echo "  Docker:  docker compose -f docker-compose.yml up -d"
echo "  Podman:  podman-compose -f docker-compose.yml up -d"
