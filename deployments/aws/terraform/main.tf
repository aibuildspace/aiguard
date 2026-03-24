# ─────────────────────────────────────────────────────────────────────────────
# AIGate — AWS Terraform Main Configuration
#
# Deploys an EC2 instance with cloud-init that installs AIGate from the
# public repo and starts the proxy as a systemd service.
# ─────────────────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge({
      Project   = "aigate"
      ManagedBy = "terraform"
    }, var.tags)
  }
}

# ── Data Sources ─────────────────────────────────────────────────────────────

# Latest Amazon Linux 2023 AMI
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Current availability zones
data "aws_availability_zones" "available" {
  state = "available"
}

# ── SSH Key Pair ─────────────────────────────────────────────────────────────

# Generate a TLS key if no public key is provided
resource "tls_private_key" "generated" {
  count     = var.ssh_public_key == "" ? 1 : 0
  algorithm = "ED25519"
}

resource "aws_key_pair" "this" {
  key_name   = var.key_pair_name
  public_key = var.ssh_public_key != "" ? var.ssh_public_key : tls_private_key.generated[0].public_key_openssh
}

# Write private key to local file when auto-generated
resource "local_file" "private_key" {
  count           = var.ssh_public_key == "" ? 1 : 0
  content         = tls_private_key.generated[0].private_key_openssh
  filename        = "${path.module}/${var.key_pair_name}.pem"
  file_permission = "0400"
}

# ── VPC & Networking ─────────────────────────────────────────────────────────

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "aigate-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "aigate-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = { Name = "aigate-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = { Name = "aigate-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Security Group ───────────────────────────────────────────────────────────

resource "aws_security_group" "this" {
  name        = "aigate-sg"
  description = "AIGate proxy — SSH + HTTP 8080"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "aigate-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  for_each = toset(var.allowed_ssh_cidrs)

  security_group_id = aws_security_group.this.id
  description       = "SSH access"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_ingress_rule" "proxy" {
  for_each = toset(var.allowed_proxy_cidrs)

  security_group_id = aws_security_group.this.id
  description       = "AIGate proxy"
  ip_protocol       = "tcp"
  from_port         = 8080
  to_port           = 8080
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.this.id
  description       = "Allow all outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ── Elastic IP ───────────────────────────────────────────────────────────────

resource "aws_eip" "this" {
  domain = "vpc"

  tags = { Name = "aigate-eip" }
}

resource "aws_eip_association" "this" {
  instance_id   = aws_instance.this.id
  allocation_id = aws_eip.this.id
}

# ── EC2 Instance ─────────────────────────────────────────────────────────────

resource "aws_instance" "this" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.this.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.this.id]

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    repo_url   = var.repo_url
    repo_branch = var.repo_branch
  })

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required"  # IMDSv2 only
    http_endpoint = "enabled"
  }

  tags = { Name = var.instance_name }
}
