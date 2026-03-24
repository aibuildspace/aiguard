# ─────────────────────────────────────────────────────────────────────────────
# AIGate — AWS Terraform Variables
# ─────────────────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type (t3.micro = free-tier eligible)"
  type        = string
  default     = "t3.micro"

  validation {
    condition     = contains(["t3.micro", "t3.small", "t3.medium", "t3.large", "t2.micro"], var.instance_type)
    error_message = "Instance type must be one of: t3.micro, t3.small, t3.medium, t3.large, t2.micro"
  }
}

variable "instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
  default     = "aigate-proxy"
}

variable "admin_username" {
  description = "OS-level admin user on the EC2 instance"
  type        = string
  default     = "ec2-user"
}

variable "ssh_public_key" {
  description = "SSH public key for EC2 access. If empty, a new key pair is generated."
  type        = string
  default     = ""
}

variable "key_pair_name" {
  description = "Name of the AWS key pair"
  type        = string
  default     = "aigate-key"
}

variable "repo_url" {
  description = "AIGate GitHub repo URL"
  type        = string
  default     = "https://github.com/aibuildspace/aigate.git"
}

variable "repo_branch" {
  description = "Git branch or tag to deploy"
  type        = string
  default     = "main"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into the instance"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "allowed_proxy_cidrs" {
  description = "CIDR blocks allowed to reach the AIGate proxy (port 8080)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 20
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
