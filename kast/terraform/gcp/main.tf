# GCP Infrastructure for OWASP ZAP Cloud Scanning
# Creates ephemeral infrastructure for running ZAP in Docker

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "google" {
  project     = var.project_id
  region      = var.region
  zone        = var.zone
  credentials = file(var.credentials_file)
}

# Generate a unique identifier for this scan
resource "random_id" "scan_id" {
  byte_length = 4
}

locals {
  scan_identifier = "kast-zap-${random_id.scan_id.hex}"
  common_labels = merge(
    var.labels,
    {
      scan_id   = random_id.scan_id.hex
      timestamp = replace(timestamp(), ":", "-")
    }
  )
}

# VPC Network
resource "google_compute_network" "zap_network" {
  name                    = "${local.scan_identifier}-network"
  auto_create_subnetworks = false

  labels = local.common_labels
}

# Subnet
resource "google_compute_subnetwork" "zap_subnet" {
  name          = "${local.scan_identifier}-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.zap_network.id
}

# Firewall rule for SSH
resource "google_compute_firewall" "zap_ssh" {
  name    = "${local.scan_identifier}-allow-ssh"
  network = google_compute_network.zap_network.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]  # TODO: Restrict to operator IP
  target_tags   = ["zap-scanner"]
}

# Firewall rule for ZAP API
resource "google_compute_firewall" "zap_api" {
  name    = "${local.scan_identifier}-allow-zap-api"
  network = google_compute_network.zap_network.name

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  source_ranges = ["0.0.0.0/0"]  # TODO: Restrict to operator IP
  target_tags   = ["zap-scanner"]
}

# Firewall rule for outbound traffic
resource "google_compute_firewall" "zap_egress" {
  name      = "${local.scan_identifier}-allow-egress"
  network   = google_compute_network.zap_network.name
  direction = "EGRESS"

  allow {
    protocol = "all"
  }

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["zap-scanner"]
}

# External IP address
resource "google_compute_address" "zap_ip" {
  name   = "${local.scan_identifier}-ip"
  region = var.region

  labels = local.common_labels
}

# Startup script for Docker and ZAP installation
locals {
  startup_script = <<-EOF
    #!/bin/bash
    set -e
    
    # Update system
    apt-get update
    apt-get upgrade -y
    
    # Install Docker
    apt-get install -y ca-certificates curl gnupg lsb-release
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Start Docker service
      systemctl start docker
      systemctl enable docker
      
      # Add default user to docker group for non-root access
      usermod -aG docker $(ls /home | head -1)
      
      # Create directories for ZAP
    mkdir -p /opt/zap/{config,reports}
    chmod -R 777 /opt/zap
    
    # Pull ZAP Docker image
    docker pull ${var.zap_docker_image}
    
    # Create ready flag
    touch /tmp/zap-ready
    
    echo "ZAP infrastructure ready"
  EOF
}

# Compute Instance (Preemptible/Spot)
resource "google_compute_instance" "zap_instance" {
  name         = "${local.scan_identifier}-instance"
  machine_type = var.machine_type
  zone         = var.zone

  # Preemptible instance (spot)
  scheduling {
    preemptible                 = var.preemptible
    automatic_restart           = false
    on_host_maintenance         = "TERMINATE"
    provisioning_model          = var.preemptible ? "SPOT" : "STANDARD"
    instance_termination_action = var.preemptible ? "DELETE" : null
  }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 30
      type  = "pd-standard"
    }
    auto_delete = true
  }

  network_interface {
    network    = google_compute_network.zap_network.name
    subnetwork = google_compute_subnetwork.zap_subnet.name

    access_config {
      nat_ip = google_compute_address.zap_ip.address
    }
  }

  metadata = {
    ssh-keys       = "ubuntu:${var.ssh_public_key}"
    startup-script = local.startup_script
  }

  tags = ["zap-scanner"]

  labels = local.common_labels
}
