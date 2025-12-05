# Azure Terraform Outputs

output "vm_id" {
  description = "Virtual machine ID"
  value       = azurerm_linux_virtual_machine.zap_vm.id
}

output "public_ip" {
  description = "Public IP address of the ZAP instance"
  value       = azurerm_public_ip.zap_pip.ip_address
}

output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.zap_rg.name
}

output "vnet_id" {
  description = "Virtual network ID"
  value       = azurerm_virtual_network.zap_vnet.id
}

output "scan_identifier" {
  description = "Unique identifier for this scan"
  value       = local.scan_identifier
}

output "ssh_user" {
  description = "SSH username for the instance"
  value       = "azureuser"
}

output "zap_api_url" {
  description = "ZAP API endpoint URL"
  value       = "http://${azurerm_public_ip.zap_pip.ip_address}:8080"
}
