#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AIGuard — Deploy to AWS EC2
#
# Creates an EC2 instance, installs AIGuard, and starts the proxy.
# Requires: AWS CLI v2 configured with appropriate credentials.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                          # Use defaults
#   ./deploy.sh --instance-type t3.small # Override instance type
#   ./deploy.sh --key-name my-keypair    # Use existing key pair
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"
REGION="${AWS_REGION:-us-east-1}"
KEY_NAME="${KEY_NAME:-aiguard-key}"
SECURITY_GROUP_NAME="aiguard-sg"
INSTANCE_NAME="aiguard-proxy"
AMI_ID=""  # Auto-detect latest Amazon Linux 2023

# ── Parse CLI args ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
        --region)        REGION="$2"; shift 2 ;;
        --key-name)      KEY_NAME="$2"; shift 2 ;;
        --ami)           AMI_ID="$2"; shift 2 ;;
        --help)
            echo "Usage: ./deploy.sh [--instance-type TYPE] [--region REGION] [--key-name NAME] [--ami AMI_ID]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "╔══════════════════════════════════════════════════════════╗"
echo "║           AIGuard — AWS EC2 Deployment                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Region:        $REGION"
echo "  Instance type: $INSTANCE_TYPE"
echo "  Key pair:      $KEY_NAME"
echo ""

# ── Verify AWS CLI ───────────────────────────────────────────────────────────
if ! command -v aws &>/dev/null; then
    echo "❌ AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    exit 1
fi

aws sts get-caller-identity --region "$REGION" >/dev/null 2>&1 || {
    echo "❌ AWS credentials not configured. Run: aws configure"
    exit 1
}

echo "✓ AWS CLI authenticated"

# ── Resolve AMI (latest Amazon Linux 2023) ───────────────────────────────────
if [[ -z "$AMI_ID" ]]; then
    echo "→ Finding latest Amazon Linux 2023 AMI..."
    AMI_ID=$(aws ec2 describe-images \
        --region "$REGION" \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-2023*-x86_64" \
                  "Name=state,Values=available" \
        --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
        --output text)
    echo "  AMI: $AMI_ID"
fi

# ── Create key pair (if needed) ──────────────────────────────────────────────
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" &>/dev/null; then
    echo "→ Creating key pair: $KEY_NAME"
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --region "$REGION" \
        --query 'KeyMaterial' \
        --output text > "${KEY_NAME}.pem"
    chmod 400 "${KEY_NAME}.pem"
    echo "  ✓ Saved private key to ${KEY_NAME}.pem"
else
    echo "  ✓ Key pair '$KEY_NAME' already exists"
fi

# ── Create security group ────────────────────────────────────────────────────
VPC_ID=$(aws ec2 describe-vpcs --region "$REGION" \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' --output text)

SG_ID=$(aws ec2 describe-security-groups --region "$REGION" \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
    echo "→ Creating security group: $SECURITY_GROUP_NAME"
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP_NAME" \
        --description "AIGuard proxy - SSH + HTTP 8080" \
        --vpc-id "$VPC_ID" \
        --region "$REGION" \
        --query 'GroupId' --output text)

    # SSH access
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --region "$REGION" \
        --protocol tcp --port 22 --cidr 0.0.0.0/0

    # AIGuard proxy port
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --region "$REGION" \
        --protocol tcp --port 8080 --cidr 0.0.0.0/0

    echo "  ✓ Security group: $SG_ID (SSH + 8080)"
else
    echo "  ✓ Security group '$SECURITY_GROUP_NAME' already exists: $SG_ID"
fi

# ── User data (cloud-init) ──────────────────────────────────────────────────
USER_DATA=$(cat <<'USERDATA'
#!/bin/bash
set -euo pipefail

# Update system
dnf update -y
dnf install -y python3.11 python3.11-pip git

# Create aiguard user
useradd -r -m -s /bin/bash aiguard

# Install AIGuard
su - aiguard -c "
    python3.11 -m pip install --user aiguard
    mkdir -p ~/aiguard && cd ~/aiguard

    # Generate default config
    cat > .env <<'EOF'
GUARD_HOST=0.0.0.0
GUARD_PORT=8080
GUARD_LOG_LEVEL=info
GUARD_PASSTHROUGH_MODE=true
GUARD_ADMIN_API_ENABLED=true
GUARD_ADMIN_API_KEY=$(python3.11 -c 'import secrets; print(secrets.token_urlsafe(32))')
GUARD_DATABASE_URL=sqlite+aiosqlite:///./aiguard.db
EOF
"

# Create systemd service
cat > /etc/systemd/system/aiguard.service <<'EOF'
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

systemctl daemon-reload
systemctl enable aiguard
systemctl start aiguard

echo "AIGuard deployment complete" > /home/aiguard/deploy.log
USERDATA
)

# ── Launch instance ──────────────────────────────────────────────────────────
echo "→ Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
    --region "$REGION" \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --user-data "$USER_DATA" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "  ✓ Instance: $INSTANCE_ID"
echo "→ Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  AIGuard deployed successfully!                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Instance:  $INSTANCE_ID"
echo "  Public IP: $PUBLIC_IP"
echo "  Proxy URL: http://$PUBLIC_IP:8080"
echo ""
echo "  SSH:       ssh -i ${KEY_NAME}.pem ec2-user@$PUBLIC_IP"
echo "  Logs:      ssh -i ${KEY_NAME}.pem ec2-user@$PUBLIC_IP journalctl -u aiguard -f"
echo ""
echo "  Configure your AI tool:"
echo "    export ANTHROPIC_BASE_URL=http://$PUBLIC_IP:8080/anthropic"
echo "    export OPENAI_BASE_URL=http://$PUBLIC_IP:8080/openai"
echo ""
echo "  ⚠️  The instance needs ~2 minutes to finish setup."
echo "  ⚠️  For production: use HTTPS (ALB/nginx), restrict security group CIDRs,"
echo "      and switch to Postgres for the database."
