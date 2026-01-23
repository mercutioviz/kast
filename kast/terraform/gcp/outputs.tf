# GCP Terraform Outputs

output "instance_id" {
  description = "Compute instance ID"
  value       = google_compute_instance.zap_instance.id
}

output "public_ip" {
  description = "Public IP address of the ZAP instance"
  value       = google_compute_address.zap_ip.address
}

output "network_id" {
  description = "VPC network ID"
  value       = google_compute_network.zap_network.id
}

output "subnet_id" {
  description = "Subnet ID"
  value       = google_compute_subnetwork.zap_subnet.id
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
  description = "ZAP API endpoint URL"
  value       = "http://${google_compute_address.zap_ip.address}:8080"
}

output "instance_type" {
  description = "Type of instance provisioned (preemptible or standard)"
  value       = var.use_preemptible_instance ? "preemptible" : "standard"
}
