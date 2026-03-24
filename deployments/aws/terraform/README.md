# Deploy AIGate on AWS (Terraform)

Deploy AIGate as a standalone proxy on an AWS EC2 instance using Terraform.
Installs from the public repo: [github.com/aibuildspace/aigate](https://github.com/aibuildspace/aigate)

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) configured (`aws configure`)
- An AWS account with EC2, VPC, and IAM permissions

## Quick Start

```bash
cd deployments/aws/terraform
chmod +x deploy.sh
./deploy.sh
```

The interactive script will:

1. Let you pick a **region** and **instance type** (arrow keys)
2. Run `terraform apply` (VPC + subnet + security group + EC2 + Elastic IP)
3. Wait for cloud-init to install AIGate from GitHub
4. Verify the service is healthy
5. **Onboard your first user** (org → user → API key)
6. Print ready-to-use `export` commands for your AI tool

## Files

| File | Description |
|---|---|
| `main.tf` | VPC, subnet, security group, EC2 instance, Elastic IP |
| `variables.tf` | All configurable inputs with defaults |
| `outputs.tf` | Public IP, SSH command, proxy URL, etc. |
| `versions.tf` | Provider version constraints |
| `cloud-init.yaml` | User-data template that installs AIGate |
| `deploy.sh` | Interactive wrapper: runs Terraform + onboards user |
| `terraform.tfvars.example` | Example variable overrides |

## Options (deploy.sh)

| Flag | Default | Description |
|---|---|---|
| `--region` | `us-east-1` | AWS region |
| `--instance-type` | `t3.micro` | EC2 instance type (t3.micro = free-tier eligible) |
| `--instance-name` | `aigate-proxy` | Name tag for the EC2 instance |
| `--branch` | `main` | Git branch/tag to deploy from |
| `--yes`, `-y` | | Skip all prompts, use defaults |
| `--destroy` | | Tear down all resources |

```bash
# Non-interactive deploy
./deploy.sh --region ap-southeast-2 --instance-type t3.small --yes

# Deploy a specific release
./deploy.sh --branch v0.2.0

# Destroy everything
./deploy.sh --destroy
```

## Terraform Variables

You can also use Terraform directly with a `terraform.tfvars` file:

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars to taste

terraform init
terraform plan
terraform apply
```

| Variable | Default | Description |
|---|---|---|
| `aws_region` | `us-east-1` | AWS region |
| `instance_type` | `t3.micro` | EC2 instance type |
| `instance_name` | `aigate-proxy` | Instance name tag |
| `ssh_public_key` | *(auto-generate)* | SSH public key; leave empty to auto-generate a key pair |
| `key_pair_name` | `aigate-key` | AWS key pair name |
| `repo_url` | `https://github.com/aibuildspace/aigate.git` | Git repo |
| `repo_branch` | `main` | Branch/tag |
| `vpc_cidr` | `10.0.0.0/16` | VPC CIDR |
| `subnet_cidr` | `10.0.1.0/24` | Subnet CIDR |
| `allowed_ssh_cidrs` | `["0.0.0.0/0"]` | CIDRs allowed SSH access |
| `allowed_proxy_cidrs` | `["0.0.0.0/0"]` | CIDRs allowed proxy access |
| `root_volume_size` | `20` | Root volume size (GB) |
| `tags` | `{}` | Additional resource tags |

## Post-Deployment

### Connect

```bash
# If Terraform generated a key pair:
ssh -i aigate-key.pem ec2-user@$(terraform output -raw public_ip)

# If you provided your own SSH key:
ssh ec2-user@$(terraform output -raw public_ip)
```

### Check status

```bash
sudo systemctl status aigate
sudo journalctl -u aigate -f
```

### Admin API key

```bash
ssh ec2-user@<PUBLIC_IP> "sudo grep ADMIN /home/aigate/aigate/.env"
```

### Manual onboarding (if skipped during deploy)

```bash
ssh ec2-user@<PUBLIC_IP>
sudo -u aigate aigate onboard
```

## Architecture

```
┌─────────────────────────────────────────────┐
│  VPC  10.0.0.0/16                           │
│  ┌────────────────────────────────────────┐  │
│  │  Public Subnet  10.0.1.0/24           │  │
│  │  ┌──────────────────────────────────┐  │  │
│  │  │  EC2 (Amazon Linux 2023)         │  │  │
│  │  │  ┌────────────────────────────┐  │  │  │
│  │  │  │  AIGate  :8080            │  │  │  │
│  │  │  └────────────────────────────┘  │  │  │
│  │  └──────────────────────────────────┘  │  │
│  └────────────────────────────────────────┘  │
│  Internet Gateway ← Elastic IP               │
└─────────────────────────────────────────────┘
```

## Production Hardening

- **HTTPS** — Place an ALB or nginx reverse proxy in front with TLS termination
- **Security group** — Restrict `allowed_ssh_cidrs` and `allowed_proxy_cidrs` to your team IP ranges
- **Database** — Switch `GUARD_DATABASE_URL` to Amazon RDS for PostgreSQL
- **Instance size** — `t3.small` or larger for sustained workloads
- **Monitoring** — Export OTLP metrics to CloudWatch or Datadog
- **State** — Store Terraform state remotely in S3 + DynamoDB locking

## Teardown

```bash
# Via deploy script
./deploy.sh --destroy

# Or directly with Terraform
cd deployments/aws/terraform
terraform destroy
```
