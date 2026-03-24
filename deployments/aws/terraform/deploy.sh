#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AIGate — Deploy to AWS via Terraform
#
# Deploys AIGate using Terraform (VPC + EC2 + cloud-init), then onboards
# the first user.
# Installs from: https://github.com/aibuildspace/aigate
#
# Requires: Terraform >= 1.5, AWS CLI v2 authenticated.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                   # Interactive prompts
#   ./deploy.sh --yes             # Accept all defaults (no prompts)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/terraform"

# ── Defaults ─────────────────────────────────────────────────────────────────
REGION="us-east-1"
INSTANCE_TYPE="t3.micro"
INSTANCE_NAME="aigate-proxy"
ADMIN_USER="ec2-user"
AUTO_YES=false
BRANCH="main"
DESTROY=false

REGIONS=("us-east-1" "us-west-2" "us-east-2" "eu-west-1" "eu-central-1" "ap-southeast-1" "ap-southeast-2" "ap-northeast-1")
INSTANCE_TYPES=("t3.micro" "t3.small" "t3.medium" "t3.large" "t2.micro")

# ── Parse CLI args ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)         REGION="$2"; shift 2 ;;
        --instance-type)  INSTANCE_TYPE="$2"; shift 2 ;;
        --instance-name)  INSTANCE_NAME="$2"; shift 2 ;;
        --branch)         BRANCH="$2"; shift 2 ;;
        --yes|-y)         AUTO_YES=true; shift ;;
        --destroy)        DESTROY=true; shift ;;
        --help)
            echo "Usage: ./deploy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --region REGION          AWS region (default: us-east-1)"
            echo "  --instance-type TYPE     EC2 instance type (default: t3.micro)"
            echo "  --instance-name NAME     Instance name tag (default: aigate-proxy)"
            echo "  --branch BRANCH          Git branch/tag to deploy (default: main)"
            echo "  --yes, -y                Skip prompts, use defaults"
            echo "  --destroy                Tear down all resources"
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
echo "║        AIGate — AWS Deployment (Terraform)             ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── Verify prerequisites ────────────────────────────────────────────────────
if ! command -v terraform &>/dev/null; then
    echo "❌ Terraform not found. Install: https://developer.hashicorp.com/terraform/install"
    exit 1
fi

if ! command -v aws &>/dev/null; then
    echo "❌ AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    exit 1
fi

aws sts get-caller-identity >/dev/null 2>&1 || {
    echo "❌ AWS credentials not configured. Run: aws configure"
    exit 1
}

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo ""
echo "  ✓ AWS Account: $ACCOUNT"

# ── Destroy mode ─────────────────────────────────────────────────────────────
if [[ "$DESTROY" == true ]]; then
    echo ""
    echo "→ Destroying all AIGate resources..."
    cd "$TF_DIR"
    terraform destroy -auto-approve \
        -var "aws_region=$REGION"
    echo "  ✓ All resources destroyed"
    exit 0
fi

# ── Interactive config ───────────────────────────────────────────────────────
REGION=$(pick "Select region" "${REGIONS[@]}")
INSTANCE_TYPE=$(pick "Select instance type" "${INSTANCE_TYPES[@]}")

if [[ "$AUTO_YES" != true ]]; then
    echo ""
    read -rp "  Instance name [$INSTANCE_NAME]: " name_input </dev/tty
    INSTANCE_NAME="${name_input:-$INSTANCE_NAME}"
fi

# ── SSH key ──────────────────────────────────────────────────────────────────
SSH_PUBLIC_KEY=""
SSH_KEY_FILE="$HOME/.ssh/id_ed25519.pub"
if [[ ! -f "$SSH_KEY_FILE" ]]; then
    SSH_KEY_FILE="$HOME/.ssh/id_rsa.pub"
fi

if [[ -f "$SSH_KEY_FILE" ]]; then
    if [[ "$AUTO_YES" != true ]]; then
        echo ""
        use_key=$(pick "Use existing SSH key ($SSH_KEY_FILE)?" "Yes — use my key" "No — generate a new one")
        if [[ "$use_key" == "Yes — use my key" ]]; then
            SSH_PUBLIC_KEY=$(cat "$SSH_KEY_FILE")
        fi
    else
        SSH_PUBLIC_KEY=$(cat "$SSH_KEY_FILE")
    fi
fi

SSH_DISPLAY="auto-generate"
if [[ -n "$SSH_PUBLIC_KEY" ]]; then
    SSH_DISPLAY="$SSH_KEY_FILE"
fi

echo ""
echo "  ┌──────────────────────────────────────────┐"
echo "  │  Region:    $REGION"
echo "  │  Instance:  $INSTANCE_TYPE"
echo "  │  Name:      $INSTANCE_NAME"
echo "  │  Branch:    $BRANCH"
echo "  │  SSH key:   $SSH_DISPLAY"
echo "  └──────────────────────────────────────────┘"
echo ""

if [[ "$AUTO_YES" != true ]]; then
    read -rp "  Proceed? [Y/n]: " confirm </dev/tty
    confirm="${confirm:-Y}"
    [[ "$confirm" =~ ^[Yy] ]] || { echo "  Aborted."; exit 0; }
fi

# ── Terraform init & apply ───────────────────────────────────────────────────
cd "$TF_DIR"

echo "→ Initialising Terraform..."
terraform init -input=false -upgrade >/dev/null 2>&1
echo "  ✓ Initialised"

echo "→ Deploying infrastructure..."
TF_ARGS=(
    -auto-approve
    -var "aws_region=$REGION"
    -var "instance_type=$INSTANCE_TYPE"
    -var "instance_name=$INSTANCE_NAME"
    -var "repo_branch=$BRANCH"
    -var "ssh_public_key=$SSH_PUBLIC_KEY"
)

terraform apply "${TF_ARGS[@]}"

PUBLIC_IP=$(terraform output -raw public_ip)
SSH_CMD=$(terraform output -raw ssh_command)
PROXY_URL=$(terraform output -raw proxy_url)

echo ""
echo "  ✓ Deployment complete"
echo "  ✓ Public IP: $PUBLIC_IP"

# ── Remove stale SSH host key ────────────────────────────────────────────────
ssh-keygen -R "$PUBLIC_IP" 2>/dev/null || true

# ── Determine SSH key for commands ───────────────────────────────────────────
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=5 -o UserKnownHostsFile=/dev/null"
if [[ -z "$SSH_PUBLIC_KEY" ]]; then
    KEY_FILE=$(terraform output -raw ssh_private_key_file)
    SSH_OPTS="$SSH_OPTS -i $KEY_FILE"
fi

# ── Wait for cloud-init ─────────────────────────────────────────────────────
echo "→ Waiting for cloud-init (2-4 minutes)..."
MAX_WAIT=300
ELAPSED=0
while (( ELAPSED < MAX_WAIT )); do
    STATUS=$(ssh $SSH_OPTS "$ADMIN_USER@$PUBLIC_IP" \
        "cloud-init status 2>/dev/null | grep -oE 'done|error|running'" 2>/dev/null || true)
    if [[ "$STATUS" == "done" ]]; then
        break
    elif [[ "$STATUS" == "error" ]]; then
        echo "  ⚠ cloud-init finished with errors"
        echo "  Check: $SSH_CMD sudo cloud-init status --long"
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
    echo "  Check: $SSH_CMD sudo journalctl -u aigate -f"
else
    echo "  ✓ AIGate is running"
fi

# ── Read admin key ───────────────────────────────────────────────────────────
ADMIN_KEY=$(ssh $SSH_OPTS "$ADMIN_USER@$PUBLIC_IP" \
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
                local payload="{\"org_id\": \"$ORG_ID\", \"user_id\": \"$USER_ID\", \"label\": \"aws-deploy-$provider\", \"provider\": \"$provider\""
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
echo "  Instance:  $INSTANCE_NAME ($INSTANCE_TYPE)"
echo "  Region:    $REGION"
echo "  Public IP: $PUBLIC_IP"
echo "  Proxy URL: http://$PUBLIC_IP:8080"
echo "  Portal:    http://$PUBLIC_IP:8080/portal"
echo ""
echo "  SSH:       $SSH_CMD"
echo "  Logs:      $SSH_CMD sudo journalctl -u aigate -f"

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
    echo "    $SSH_CMD"
    echo "    sudo -u aigate aigate onboard"
fi

echo ""
echo "  Configure your AI tools:"
echo "    aigate setup"
echo ""
echo "  Teardown:  cd deployments/aws && ./deploy.sh --destroy"
echo ""
echo "  ⚠️  For production: add HTTPS (ALB/nginx), restrict security group CIDRs,"
echo "      and switch to managed PostgreSQL (RDS)."
echo ""
