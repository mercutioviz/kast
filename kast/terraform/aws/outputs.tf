# AWS Terraform Outputs
# Conditionally outputs based on spot vs on-demand instance

output "instance_id" {
  description = "EC2 instance ID"
  value       = var.use_spot_instance ? aws_spot_instance_request.zap_spot[0].spot_instance_id : aws_instance.zap_ondemand[0].id
}

output "public_ip" {
  description = "Public IP address of the ZAP instance (ephemeral)"
  value       = var.use_spot_instance ? aws_spot_instance_request.zap_spot[0].public_ip : aws_instance.zap_ondemand[0].public_ip
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.zap_vpc.id
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.zap_sg.id
}

output "scan_identifier" {
  description = "Unique identifier for this scan"
  value       = local.scan_identifier
}

output "ssh_user" {
  description = "SSH username for the instance"
  value       = "ubuntu"
}

output "zap_api_url" {
  description = "URL for ZAP API access"
  value       = var.use_spot_instance ? "http://${aws_spot_instance_request.zap_spot[0].public_ip}:8080" : "http://${aws_instance.zap_ondemand[0].public_ip}:8080"
}

output "instance_type" {
  description = "Type of instance provisioned (spot or on-demand)"
  value       = var.use_spot_instance ? "spot" : "on-demand"
}
