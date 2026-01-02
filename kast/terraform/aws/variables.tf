# AWS Terraform Variables
# Note: AWS credentials are automatically resolved by the AWS provider via:
# - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
# - AWS CLI credentials (~/.aws/credentials)
# - IAM instance profiles (if running on EC2)

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "ami_id" {
  description = "AMI ID (leave empty for latest Ubuntu 22.04)"
  type        = string
  default     = ""
}

variable "spot_max_price" {
  description = "Maximum price for spot instance (USD/hour)"
  type        = string
  default     = "0.05"
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

variable "zap_api_key" {
  description = "ZAP API key for authentication"
  type        = string
  default     = "kast01"
  sensitive   = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project    = "KAST"
    ManagedBy  = "KAST-ZAP-Plugin"
    Environment = "security-scan"
  }
}
