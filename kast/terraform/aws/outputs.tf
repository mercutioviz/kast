# AWS Terraform Outputs

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_spot_instance_request.zap_instance.spot_instance_id
}

output "public_ip" {
  description = "Public IP address of the ZAP instance (ephemeral)"
  value       = aws_spot_instance_request.zap_instance.public_ip
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
  value       = "http://${aws_spot_instance_request.zap_instance.public_ip}:8080"
}
