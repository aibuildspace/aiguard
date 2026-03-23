#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AIGuard — Deploy to Azure Virtual Machine
#
# Creates a VM, installs AIGuard, and starts the proxy.
# Requires: Azure CLI (az) authenticated.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                              # Use defaults
#   ./deploy.sh --vm-size Standard_B2s       # Override VM size
#   ./deploy.sh --location westeurope        # Override location
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-aiguard-rg}"
LOCATION="${LOCATION:-eastus}"
VM_NAME="${VM_NAME:-aiguard-vm}"
VM_SIZE="${VM_SIZE:-Standard_B1s}"
ADMIN_USER="azureuser"
IMAGE="Canonical:ubuntu-24_04-lts:server:latest"

# ── Parse CLI args ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
        --location)       LOCATION="$2"; shift 2 ;;
        --vm-name)        VM_NAME="$2"; shift 2 ;;
        --vm-size)        VM_SIZE="$2"; shift 2 ;;
        --help)
            echo "Usage: ./deploy.sh [--resource-group RG] [--location LOC] [--vm-name NAME] [--vm-size SIZE]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "╔══════════════════════════════════════════════════════════╗"
echo "║        AIGuard — Azure VM Deployment                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Resource group: $RESOURCE_GROUP"
echo "  Location:       $LOCATION"
echo "  VM name:        $VM_NAME"
echo "  VM size:        $VM_SIZE"
echo ""

# ── Verify Azure CLI ────────────────────────────────────────────────────────
if ! command -v az &>/dev/null; then
    echo "❌ Azure CLI not found. Install: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

az account show >/dev/null 2>&1 || {
    echo "❌ Not logged in. Run: az login"
    exit 1
}

SUBSCRIPTION=$(az account show --query name --output tsv)
echo "✓ Azure CLI authenticated (subscription: $SUBSCRIPTION)"

# ── Create resource group ────────────────────────────────────────────────────
echo "→ Creating resource group: $RESOURCE_GROUP"
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none

echo "  ✓ Resource group ready"

# ── Cloud-init script ───────────────────────────────────────────────────────
CLOUD_INIT=$(cat <<'CLOUDINIT'
#cloud-config
package_update: true
package_upgrade: true

packages:
  - python3-pip
  - python3-venv
  - git

runcmd:
  # Create aiguard user
  - useradd -r -m -s /bin/bash aiguard

  # Install AIGuard
  - su - aiguard -c "python3 -m pip install --user --break-system-packages aiguard"
  - su - aiguard -c "mkdir -p ~/aiguard"

  # Generate config
  - |
    ADMIN_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    cat > /home/aiguard/aiguard/.env <<EOF
    GUARD_HOST=0.0.0.0
    GUARD_PORT=8080
    GUARD_LOG_LEVEL=info
    GUARD_PASSTHROUGH_MODE=true
    GUARD_ADMIN_API_ENABLED=true
    GUARD_ADMIN_API_KEY=$ADMIN_KEY
    GUARD_DATABASE_URL=sqlite+aiosqlite:///./aiguard.db
    EOF
    chown aiguard:aiguard /home/aiguard/aiguard/.env
    # Trim leading whitespace from heredoc
    sed -i 's/^[[:space:]]*//' /home/aiguard/aiguard/.env

  # Create systemd service
  - |
    cat > /etc/systemd/system/aiguard.service <<EOF
    [Unit]
    Description=AIGuard LLM Security Proxy
    After=network.target

    [Service]
    Type=simple
    User=aiguard
    WorkingDirectory=/home/aiguard/aiguard
    ExecStart=/home/aiguard/.local/bin/guard start --host 0.0.0.0 --port 8080
    Restart=always
    RestartSec=5
    Environment=PATH=/home/aiguard/.local/bin:/usr/bin:/bin

    [Install]
    WantedBy=multi-user.target
    EOF
    sed -i 's/^[[:space:]]*//' /etc/systemd/system/aiguard.service

  - systemctl daemon-reload
  - systemctl enable aiguard
  - systemctl start aiguard
CLOUDINIT
)

# Write cloud-init to temp file
CLOUD_INIT_FILE=$(mktemp /tmp/aiguard-cloud-init-XXXXXX.yaml)
echo "$CLOUD_INIT" > "$CLOUD_INIT_FILE"

# ── Create VM ────────────────────────────────────────────────────────────────
echo "→ Creating VM: $VM_NAME ($VM_SIZE)..."
az vm create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --image "$IMAGE" \
    --size "$VM_SIZE" \
    --admin-username "$ADMIN_USER" \
    --generate-ssh-keys \
    --custom-data "$CLOUD_INIT_FILE" \
    --public-ip-sku Standard \
    --output none

rm -f "$CLOUD_INIT_FILE"
echo "  ✓ VM created"

# ── Open port 8080 ──────────────────────────────────────────────────────────
echo "→ Opening port 8080..."
az vm open-port \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --port 8080 \
    --priority 1010 \
    --output none

echo "  ✓ Port 8080 open"

# ── Get public IP ────────────────────────────────────────────────────────────
PUBLIC_IP=$(az vm show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --show-details \
    --query publicIps \
    --output tsv)

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  AIGuard deployed successfully!                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  VM:        $VM_NAME"
echo "  Public IP: $PUBLIC_IP"
echo "  Proxy URL: http://$PUBLIC_IP:8080"
echo ""
echo "  SSH:       ssh $ADMIN_USER@$PUBLIC_IP"
echo "  Logs:      ssh $ADMIN_USER@$PUBLIC_IP sudo journalctl -u aiguard -f"
echo ""
echo "  Configure your AI tool:"
echo "    export ANTHROPIC_BASE_URL=http://$PUBLIC_IP:8080/anthropic"
echo "    export OPENAI_BASE_URL=http://$PUBLIC_IP:8080/openai"
echo ""
echo "  ⚠️  The VM needs ~3 minutes to finish cloud-init setup."
echo "  ⚠️  For production: use HTTPS (App Gateway/nginx), restrict NSG rules,"
echo "      and switch to Azure Database for PostgreSQL."
