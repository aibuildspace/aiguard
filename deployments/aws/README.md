# Deploy AIGate on AWS EC2

Deploy AIGate as a standalone proxy on an Amazon EC2 instance.

## Prerequisites

- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) installed and configured
- An AWS account with EC2 permissions
- A default VPC in your target region

## Quick Start

```bash
cd deployments/aws
chmod +x deploy.sh
./deploy.sh
```

This will:

1. Find the latest Amazon Linux 2023 AMI
2. Create a key pair (`aigate-key.pem`) if one doesn't exist
3. Create a security group allowing SSH (22) and AIGate (8080)
4. Launch a `t3.micro` instance with cloud-init that installs AIGate
5. Print the public IP and connection details

## Options

| Flag | Default | Description |
|---|---|---|
| `--instance-type` | `t3.micro` | EC2 instance type |
| `--region` | `us-east-1` | AWS region |
| `--key-name` | `aigate-key` | SSH key pair name |
| `--ami` | *(auto-detect)* | Override AMI ID |

```bash
# Example: larger instance in eu-west-1
./deploy.sh --instance-type t3.small --region eu-west-1
```

## Post-Deployment

### Connect

```bash
ssh -i aigate-key.pem ec2-user@<PUBLIC_IP>
```

### Check status

```bash
sudo systemctl status aigate
sudo journalctl -u aigate -f
```

### Configure your AI tools

```bash
export ANTHROPIC_BASE_URL=http://<PUBLIC_IP>:8080/anthropic
export OPENAI_BASE_URL=http://<PUBLIC_IP>:8080/openai
```

### Admin API key

The deploy script auto-generates an admin key. Retrieve it from the instance:

```bash
ssh -i aigate-key.pem ec2-user@<PUBLIC_IP> "cat /home/aigate/aigate/.env | grep ADMIN"
```

## Production Hardening

For production use, consider:

- **HTTPS** — Place an ALB or nginx reverse proxy in front with TLS termination
- **Security group** — Restrict ingress CIDRs to your team's IP ranges
- **Database** — Switch `GUARD_DATABASE_URL` to a managed Postgres (RDS)
- **Instance size** — `t3.small` or larger for sustained workloads
- **Monitoring** — Export OTLP metrics to CloudWatch or Datadog

## Teardown

```bash
# Find and terminate the instance
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=aigate-proxy" "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text)

aws ec2 terminate-instances --instance-ids "$INSTANCE_ID"

# Optionally clean up security group and key pair
aws ec2 delete-security-group --group-name aigate-sg
aws ec2 delete-key-pair --key-name aigate-key
rm -f aigate-key.pem
```
