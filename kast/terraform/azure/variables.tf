# Azure Terraform Variables

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
  sensitive   = true
}

variable "tenant_id" {
  description = "Azure tenant ID"
  type        = string
  sensitive   = true
}

variable "client_id" {
  description = "Azure client ID"
  type        = string
  sensitive   = true
}

variable "client_secret" {
  description = "Azure client secret"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "vm_size" {
  description = "Azure VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "use_spot_instance" {
  description = "Use spot instance (true) or standard (false)"
  type        = bool
  default     = true
}

variable "spot_max_price" {
  description = "Maximum price for spot instance (-1 for regular price)"
  type        = number
  default     = -1
}

variable "ssh_public_key" {
  description = "SSH public key for instance access"
  type        = string
}

variable "zap_docker_image" {
  description = "ZAP Docker image to use"
  type        = string
  default     = "ghcr.io/zaproxy/zaproxy:stable"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "KAST"
    ManagedBy   = "KAST-ZAP-Plugin"
    Environment = "security-scan"
  }
}
