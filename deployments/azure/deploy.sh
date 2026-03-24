#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AIGate — Deploy to Azure via Bicep
#
# Deploys AIGate using an ARM/Bicep template, then onboards the first user.
# Installs from: https://github.com/aibuildspace/aigate
#
# Requires: Azure CLI (az) authenticated, with Bicep support.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                   # Interactive prompts
#   ./deploy.sh --yes             # Accept all defaults (no prompts)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Defaults ─────────────────────────────────────────────────────────────────
RESOURCE_GROUP="aigate-rg"
LOCATION="eastus"
VM_NAME="aigate-vm"
VM_SIZE="Standard_B1s"
ADMIN_USER="azureuser"
AUTO_YES=false
BRANCH="main"

LOCATIONS=("eastus" "westus" "centralus" "westus2" "northeurope" "westeurope" "southeastasia" "australiaeast")
VM_SIZES=("Standard_B1s" "Standard_B1ls" "Standard_B2s" "Standard_B2ats_v2" "Standard_DS1_v2")

# ── Parse CLI args ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
        --location)       LOCATION="$2"; shift 2 ;;
        --vm-name)        VM_NAME="$2"; shift 2 ;;
        --vm-size)        VM_SIZE="$2"; shift 2 ;;
        --branch)         BRANCH="$2"; shift 2 ;;
        --yes|-y)         AUTO_YES=true; shift ;;
        --help)
            echo "Usage: ./deploy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --location LOC         Azure region (default: eastus)"
            echo "  --vm-size SIZE         VM size (default: Standard_B1s)"
            echo "  --vm-name NAME         VM name (default: aigate-vm)"
            echo "  --resource-group RG    Resource group (default: aigate-rg)"
            echo "  --branch BRANCH        Git branch/tag to deploy (default: main)"
            echo "  --yes, -y              Skip prompts, use defaults"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Helper: arrow-key picker ────────────────────────────────────────────────
pick() {
    local prompt="$1"; shift
    local -a options=("$@")
    local selected=0
    local count=${#options[@]}

    if [[ "$AUTO_YES" == true ]]; then
        echo "${options[0]}"
        return
    fi

    printf '\e[?25l' >&2

    _draw_menu() {
        for i in "${!options[@]}"; do
            if (( i == selected )); then
                printf '  \e[36m→ %s\e[0m\n' "${options[$i]}" >&2
            else
                printf '    %s\n' "${options[$i]}" >&2
            fi
        done
    }

    echo "" >&2
    echo "  $prompt (↑/↓ then Enter):" >&2
    echo "" >&2
    _draw_menu

    while true; do
        IFS= read -rsn1 key </dev/tty
        case "$key" in
            $'\x1b')
                read -rsn2 rest </dev/tty
                case "$rest" in
                    '[A') (( selected > 0 )) && (( selected-- )) ;;
                    '[B') (( selected < count - 1 )) && (( selected++ )) ;;
                esac
                ;;
            '') break ;;
            *) continue ;;
        esac
        printf '\e[%dA' "$count" >&2
        _draw_menu
    done

    printf '\e[?25h' >&2
    echo "${options[$selected]}"
}

# ── Banner ───────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║        AIGate — Azure Deployment (Bicep)               ║"
echo "╚══════════════════════════════════════════════════════════╝"

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
echo ""
echo "  ✓ Subscription: $SUBSCRIPTION"

# ── Interactive config ───────────────────────────────────────────────────────
LOCATION=$(pick "Select region" "${LOCATIONS[@]}")
VM_SIZE=$(pick "Select VM size" "${VM_SIZES[@]}")

if [[ "$AUTO_YES" != true ]]; then
    echo ""
    read -rp "  Resource group [$RESOURCE_GROUP]: " rg </dev/tty
    RESOURCE_GROUP="${rg:-$RESOURCE_GROUP}"
    read -rp "  VM name [$VM_NAME]: " vn </dev/tty
    VM_NAME="${vn:-$VM_NAME}"
fi

# ── SSH key ──────────────────────────────────────────────────────────────────
SSH_KEY_FILE="$HOME/.ssh/id_rsa.pub"
if [[ ! -f "$SSH_KEY_FILE" ]]; then
    SSH_KEY_FILE="$HOME/.ssh/id_ed25519.pub"
fi
if [[ ! -f "$SSH_KEY_FILE" ]]; then
    echo "→ Generating SSH key pair..."
    ssh-keygen -t ed25519 -f "$HOME/.ssh/id_ed25519" -N "" -q
    SSH_KEY_FILE="$HOME/.ssh/id_ed25519.pub"
fi
SSH_PUBLIC_KEY=$(cat "$SSH_KEY_FILE")

echo ""
echo "  ┌──────────────────────────────────────────┐"
echo "  │  Region:    $LOCATION"
echo "  │  VM size:   $VM_SIZE"
echo "  │  VM name:   $VM_NAME"
echo "  │  RG:        $RESOURCE_GROUP"
echo "  │  Branch:    $BRANCH"
echo "  │  SSH key:   $SSH_KEY_FILE"
echo "  └──────────────────────────────────────────┘"
echo ""

if [[ "$AUTO_YES" != true ]]; then
    read -rp "  Proceed? [Y/n]: " confirm </dev/tty
    confirm="${confirm:-Y}"
    [[ "$confirm" =~ ^[Yy] ]] || { echo "  Aborted."; exit 0; }
fi

# ── Resource group ───────────────────────────────────────────────────────────
echo "→ Resource group: $RESOURCE_GROUP"
EXISTING_RG_LOCATION=$(az group show --name "$RESOURCE_GROUP" --query location --output tsv 2>/dev/null || true)

if [[ -n "$EXISTING_RG_LOCATION" ]]; then
    if [[ "$EXISTING_RG_LOCATION" == "$LOCATION" ]]; then
        echo "  ✓ Already exists in $LOCATION — reusing"
    else
        echo "  ⚠ Exists in $EXISTING_RG_LOCATION, you selected $LOCATION"
        if [[ "$AUTO_YES" == true ]]; then
            do_delete_rg="Y"
        else
            read -rp "  Delete and recreate in $LOCATION? [Y/n]: " do_delete_rg </dev/tty
            do_delete_rg="${do_delete_rg:-Y}"
        fi
        if [[ "$do_delete_rg" =~ ^[Yy] ]]; then
            echo "  → Deleting resource group (this may take a minute)..."
            az group delete --name "$RESOURCE_GROUP" --yes --output none
            az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
            echo "  ✓ Recreated in $LOCATION"
        else
            echo "  Aborted."
            exit 0
        fi
    fi
else
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
    echo "  ✓ Created"
fi

# ── Check existing VM ────────────────────────────────────────────────────────
EXISTING_VM=$(az vm show --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query name --output tsv 2>/dev/null || true)

if [[ -n "$EXISTING_VM" ]]; then
    echo "→ VM '$VM_NAME' already exists"
    if [[ "$AUTO_YES" == true ]]; then
        do_delete_vm="Y"
    else
        read -rp "  Delete and redeploy? [Y/n]: " do_delete_vm </dev/tty
        do_delete_vm="${do_delete_vm:-Y}"
    fi
    if [[ "$do_delete_vm" =~ ^[Yy] ]]; then
        echo "  → Deleting existing resources..."
        az group delete --name "$RESOURCE_GROUP" --yes --output none
        az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
        echo "  ✓ Clean slate"
    else
        echo "  Aborted."
        exit 0
    fi
fi

# ── Deploy Bicep template ───────────────────────────────────────────────────
echo "→ Deploying Bicep template..."
DEPLOY_OUTPUT=$(az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file "$SCRIPT_DIR/main.bicep" \
    --parameters \
        vmName="$VM_NAME" \
        vmSize="$VM_SIZE" \
        adminUsername="$ADMIN_USER" \
        sshPublicKey="$SSH_PUBLIC_KEY" \
        repoBranch="$BRANCH" \
    --query "properties.outputs" \
    --output json)

PUBLIC_IP=$(echo "$DEPLOY_OUTPUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['publicIpAddress']['value'])")
echo "  ✓ Deployment complete"
echo "  ✓ Public IP: $PUBLIC_IP"

# ── Remove stale SSH host key ────────────────────────────────────────────────
ssh-keygen -R "$PUBLIC_IP" 2>/dev/null || true

# ── Wait for cloud-init ─────────────────────────────────────────────────────
echo "→ Waiting for cloud-init (2-4 minutes)..."
MAX_WAIT=300
ELAPSED=0
while (( ELAPSED < MAX_WAIT )); do
    STATUS=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o UserKnownHostsFile=/dev/null \
        "$ADMIN_USER@$PUBLIC_IP" \
        "cloud-init status 2>/dev/null | grep -oE 'done|error|running'" 2>/dev/null || true)
    if [[ "$STATUS" == "done" ]]; then
        break
    elif [[ "$STATUS" == "error" ]]; then
        echo "  ⚠ cloud-init finished with errors"
        echo "  Check: ssh $ADMIN_USER@$PUBLIC_IP sudo cloud-init status --long"
        break
    fi
    printf "  ⏳ %ds...\r" "$ELAPSED"
    sleep 15
    (( ELAPSED += 15 ))
done

if (( ELAPSED >= MAX_WAIT )); then
    echo "  ⚠ Timed out — cloud-init may still be running"
fi
echo "  ✓ Cloud-init complete"

# ── Wait for AIGate health ─────────────────────────────────────────────────
echo "→ Waiting for AIGate service..."
SVC_WAIT=90
SVC_ELAPSED=0
while (( SVC_ELAPSED < SVC_WAIT )); do
    if curl -sf "http://$PUBLIC_IP:8080/health" >/dev/null 2>&1; then
        break
    fi
    sleep 5
    (( SVC_ELAPSED += 5 ))
done

if ! curl -sf "http://$PUBLIC_IP:8080/health" >/dev/null 2>&1; then
    echo "  ⚠ Service not responding yet"
    echo "  Check: ssh $ADMIN_USER@$PUBLIC_IP sudo journalctl -u aigate -f"
else
    echo "  ✓ AIGate is running"
fi

# ── Read admin key ───────────────────────────────────────────────────────────
ADMIN_KEY=$(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$ADMIN_USER@$PUBLIC_IP" \
    "sudo grep GUARD_ADMIN_API_KEY /home/aigate/aigate/.env | cut -d= -f2" 2>/dev/null || true)

# ── Onboard first user ──────────────────────────────────────────────────────
echo ""
echo "→ Setting up first organisation and user..."

if [[ "$AUTO_YES" != true ]]; then
    read -rp "  Organisation name [default]: " onboard_org </dev/tty
    onboard_org="${onboard_org:-default}"
    read -rp "  User email: " onboard_email </dev/tty
    if [[ -z "$onboard_email" ]]; then
        onboard_email=""
    fi
    if [[ -n "$onboard_email" ]]; then
        onboard_provider=$(pick "LLM provider" "anthropic" "openai" "any")
        echo ""
        if [[ "$onboard_provider" == "openai" || "$onboard_provider" == "any" ]]; then
            read -rsp "  OpenAI API key (sk-...): " upstream_openai </dev/tty
            echo "" >&2
        fi
        if [[ "$onboard_provider" == "anthropic" || "$onboard_provider" == "any" ]]; then
            read -rsp "  Anthropic API key (sk-ant-...): " upstream_anthropic </dev/tty
            echo "" >&2
        fi
    fi
else
    onboard_org="default"
    onboard_email=""
fi

API_BASE="http://$PUBLIC_IP:8080/api/v1"
FULL_KEY=""

if [[ -n "${onboard_email:-}" && -n "${ADMIN_KEY:-}" ]]; then
    # Create org
    ORG_RESPONSE=$(curl -sf -X POST "$API_BASE/orgs" \
        -H "Content-Type: application/json" \
        -H "X-Admin-Key: $ADMIN_KEY" \
        -d "{\"name\": \"$onboard_org\"}" 2>/dev/null || true)

    if [[ -n "$ORG_RESPONSE" ]]; then
        ORG_ID=$(echo "$ORG_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" 2>/dev/null)
        ORG_SLUG=$(echo "$ORG_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['slug'])" 2>/dev/null)
        echo "  ✓ Organisation: $onboard_org (slug: $ORG_SLUG)"
    else
        ORG_SLUG=$(echo "$onboard_org" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/^-//;s/-$//' | cut -c1-32)
        ORG_ID=$(curl -sf "$API_BASE/orgs" \
            -H "X-Admin-Key: $ADMIN_KEY" 2>/dev/null \
            | python3 -c "import json,sys; orgs=json.load(sys.stdin); print(next((o['id'] for o in orgs if o['slug']=='$ORG_SLUG'),''))" 2>/dev/null || true)
        if [[ -n "$ORG_ID" ]]; then
            echo "  ✓ Organisation: $onboard_org (existing)"
        else
            echo "  ⚠ Could not create organisation — service may not be ready yet"
        fi
    fi

    if [[ -n "${ORG_ID:-}" ]]; then
        # Create user
        USER_RESPONSE=$(curl -sf -X POST "$API_BASE/users" \
            -H "Content-Type: application/json" \
            -H "X-Admin-Key: $ADMIN_KEY" \
            -d "{\"org_id\": \"$ORG_ID\", \"email\": \"$onboard_email\", \"name\": \"${onboard_email%%@*}\", \"role\": \"admin\"}" 2>/dev/null || true)

        if [[ -n "$USER_RESPONSE" ]]; then
            USER_ID=$(echo "$USER_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" 2>/dev/null)
            echo "  ✓ User: $onboard_email"
        else
            USER_ID=$(curl -sf "$API_BASE/users" \
                -H "X-Admin-Key: $ADMIN_KEY" 2>/dev/null \
                | python3 -c "import json,sys; users=json.load(sys.stdin); print(next((u['id'] for u in users if u['email']=='$onboard_email'),''))" 2>/dev/null || true)
            if [[ -n "$USER_ID" ]]; then
                echo "  ✓ User: $onboard_email (existing)"
            fi
        fi

        if [[ -n "${USER_ID:-}" ]]; then
            create_api_key() {
                local provider="$1" upstream_key="${2:-}"
                local payload="{\"org_id\": \"$ORG_ID\", \"user_id\": \"$USER_ID\", \"label\": \"azure-deploy-$provider\", \"provider\": \"$provider\""
                if [[ -n "$upstream_key" ]]; then
                    payload="$payload, \"upstream_key\": \"$upstream_key\""
                fi
                payload="$payload}"
                curl -sf -X POST "$API_BASE/keys" \
                    -H "Content-Type: application/json" \
                    -H "X-Admin-Key: $ADMIN_KEY" \
                    -d "$payload" 2>/dev/null || true
            }

            if [[ "$onboard_provider" == "any" ]]; then
                # Create separate keys per provider with their upstream keys
                OPENAI_KEY_RESPONSE=$(create_api_key "openai" "${upstream_openai:-}")
                ANTHROPIC_KEY_RESPONSE=$(create_api_key "anthropic" "${upstream_anthropic:-}")

                if [[ -n "$OPENAI_KEY_RESPONSE" ]]; then
                    OPENAI_FULL_KEY=$(echo "$OPENAI_KEY_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['key'])" 2>/dev/null)
                    OPENAI_KEY_PREFIX=$(echo "$OPENAI_KEY_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['key_prefix'])" 2>/dev/null)
                    echo "  ✓ OpenAI API Key: ${OPENAI_KEY_PREFIX}…"
                fi
                if [[ -n "$ANTHROPIC_KEY_RESPONSE" ]]; then
                    ANTHROPIC_FULL_KEY=$(echo "$ANTHROPIC_KEY_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['key'])" 2>/dev/null)
                    ANTHROPIC_KEY_PREFIX=$(echo "$ANTHROPIC_KEY_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['key_prefix'])" 2>/dev/null)
                    echo "  ✓ Anthropic API Key: ${ANTHROPIC_KEY_PREFIX}…"
                fi
            else
                # Single provider
                UPSTREAM_KEY=""
                if [[ "$onboard_provider" == "openai" ]]; then
                    UPSTREAM_KEY="${upstream_openai:-}"
                elif [[ "$onboard_provider" == "anthropic" ]]; then
                    UPSTREAM_KEY="${upstream_anthropic:-}"
                fi

                KEY_RESPONSE=$(create_api_key "$onboard_provider" "$UPSTREAM_KEY")

                if [[ -n "$KEY_RESPONSE" ]]; then
                    FULL_KEY=$(echo "$KEY_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['key'])" 2>/dev/null)
                    KEY_PREFIX=$(echo "$KEY_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['key_prefix'])" 2>/dev/null)
                    echo "  ✓ API Key: ${KEY_PREFIX}…"
                fi
            fi
        fi
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  AIGate deployed successfully!                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  VM:        $VM_NAME ($VM_SIZE)"
echo "  Region:    $LOCATION"
echo "  Public IP: $PUBLIC_IP"
echo "  Proxy URL: http://$PUBLIC_IP:8080"
echo "  Portal:    http://$PUBLIC_IP:8080/portal"
echo ""
echo "  SSH:       ssh $ADMIN_USER@$PUBLIC_IP"
echo "  Logs:      ssh $ADMIN_USER@$PUBLIC_IP sudo journalctl -u aigate -f"

# Show API key(s)
if [[ -n "${OPENAI_FULL_KEY:-}" || -n "${ANTHROPIC_FULL_KEY:-}" ]]; then
    echo ""
    echo "  ┌──────────────────────────────────────────────────────┐"
    echo "  │  🔑 Your API Keys (save them — shown only once):    │"
    echo "  └──────────────────────────────────────────────────────┘"
    [[ -n "${OPENAI_FULL_KEY:-}" ]]    && echo "  OpenAI:    $OPENAI_FULL_KEY"
    [[ -n "${ANTHROPIC_FULL_KEY:-}" ]] && echo "  Anthropic: $ANTHROPIC_FULL_KEY"
elif [[ -n "${FULL_KEY:-}" ]]; then
    echo ""
    echo "  ┌──────────────────────────────────────────────────────┐"
    echo "  │  🔑 Your API Key (save it — shown only once):       │"
    echo "  │                                                      │"
    echo "  │  $FULL_KEY"
    echo "  │                                                      │"
    echo "  └──────────────────────────────────────────────────────┘"
else
    echo ""
    echo "  To create a user + API key:"
    echo "    ssh $ADMIN_USER@$PUBLIC_IP"
    echo "    sudo -u aigate aigate onboard"
fi

echo ""
echo "  Configure your AI tools:"
echo "    aigate setup"
echo ""
echo "  Teardown:  az group delete --name $RESOURCE_GROUP --yes --no-wait"
echo ""
echo "  ⚠️  For production: add HTTPS, restrict NSG rules, use managed PostgreSQL."
echo ""