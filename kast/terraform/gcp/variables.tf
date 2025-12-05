# GCP Terraform Variables

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "credentials_file" {
  description = "Path to GCP credentials JSON file"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "machine_type" {
  description = "GCP machine type"
  type        = string
  default     = "n1-standard-2"
}

variable "preemptible" {
  description = "Use preemptible (spot) instance"
  type        = bool
  default     = true
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

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {
    project     = "kast"
    managed_by  = "kast-zap-plugin"
    environment = "security-scan"
  }
}
