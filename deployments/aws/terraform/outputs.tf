# ─────────────────────────────────────────────────────────────────────────────
# AIGuard — Terraform Outputs
# ─────────────────────────────────────────────────────────────────────────────

output "public_ip" {
  description = "Public IP address of the AIGuard instance"
  value       = aws_eip.this.public_ip
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.this.id
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = var.ssh_public_key != "" ? "ssh ${var.admin_username}@${aws_eip.this.public_ip}" : "ssh -i ${var.key_pair_name}.pem ${var.admin_username}@${aws_eip.this.public_ip}"
}

output "proxy_url" {
  description = "AIGuard proxy base URL"
  value       = "http://${aws_eip.this.public_ip}:8080"
}

output "portal_url" {
  description = "AIGuard management portal URL"
  value       = "http://${aws_eip.this.public_ip}:8080/portal"
}

output "ssh_private_key_file" {
  description = "Path to auto-generated SSH private key (empty if you supplied your own)"
  value       = var.ssh_public_key == "" ? "${path.module}/${var.key_pair_name}.pem" : ""
}

output "ami_id" {
  description = "AMI used for the instance"
  value       = data.aws_ami.al2023.id
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.this.id
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.this.id
}
