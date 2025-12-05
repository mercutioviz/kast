# Azure Infrastructure for OWASP ZAP Cloud Scanning
# Creates ephemeral infrastructure for running ZAP in Docker

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
  
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  client_id       = var.client_id
  client_secret   = var.client_secret
}

# Generate a unique identifier for this scan
resource "random_id" "scan_id" {
  byte_length = 4
}

locals {
  scan_identifier = "kast-zap-${random_id.scan_id.hex}"
  common_tags = merge(
    var.tags,
    {
      ScanID    = random_id.scan_id.hex
      Timestamp = timestamp()
    }
  )
}

# Resource Group
resource "azurerm_resource_group" "zap_rg" {
  name     = "${local.scan_identifier}-rg"
  location = var.region

  tags = local.common_tags
}

# Virtual Network
resource "azurerm_virtual_network" "zap_vnet" {
  name                = "${local.scan_identifier}-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.zap_rg.location
  resource_group_name = azurerm_resource_group.zap_rg.name

  tags = local.common_tags
}

# Subnet
resource "azurerm_subnet" "zap_subnet" {
  name                 = "${local.scan_identifier}-subnet"
  resource_group_name  = azurerm_resource_group.zap_rg.name
  virtual_network_name = azurerm_virtual_network.zap_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Network Security Group
resource "azurerm_network_security_group" "zap_nsg" {
  name                = "${local.scan_identifier}-nsg"
  location            = azurerm_resource_group.zap_rg.location
  resource_group_name = azurerm_resource_group.zap_rg.name

  # SSH access
  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # ZAP API access
  security_rule {
    name                       = "ZAP-API"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8080"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Allow all outbound
  security_rule {
    name                       = "AllowAllOutbound"
    priority                   = 1003
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.common_tags
}

# Public IP
resource "azurerm_public_ip" "zap_pip" {
  name                = "${local.scan_identifier}-pip"
  location            = azurerm_resource_group.zap_rg.location
  resource_group_name = azurerm_resource_group.zap_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = local.common_tags
}

# Network Interface
resource "azurerm_network_interface" "zap_nic" {
  name                = "${local.scan_identifier}-nic"
  location            = azurerm_resource_group.zap_rg.location
  resource_group_name = azurerm_resource_group.zap_rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.zap_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.zap_pip.id
  }

  tags = local.common_tags
}

# Associate NSG with NIC
resource "azurerm_network_interface_security_group_association" "zap_nic_nsg" {
  network_interface_id      = azurerm_network_interface.zap_nic.id
  network_security_group_id = azurerm_network_security_group.zap_nsg.id
}

# Cloud-init script
locals {
  custom_data = base64encode(<<-EOF
    #cloud-config
    package_update: true
    package_upgrade: true
    
    packages:
      - ca-certificates
      - curl
      - gnupg
      - lsb-release
    
    runcmd:
      # Install Docker
      - mkdir -p /etc/apt/keyrings
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
      - apt-get update
      - apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
      - systemctl start docker
      - systemctl enable docker
      # Add azureuser to docker group for non-root access
      - usermod -aG docker azureuser
      # Create directories for ZAP
      - mkdir -p /opt/zap/config
      - mkdir -p /opt/zap/reports
      - chmod -R 777 /opt/zap
      # Pull ZAP Docker image
      - docker pull ${var.zap_docker_image}
      # Create ready flag
      - touch /tmp/zap-ready
      - echo "ZAP infrastructure ready"
  EOF
  )
}

# Virtual Machine (Spot Instance)
resource "azurerm_linux_virtual_machine" "zap_vm" {
  name                = "${local.scan_identifier}-vm"
  location            = azurerm_resource_group.zap_rg.location
  resource_group_name = azurerm_resource_group.zap_rg.name
  size                = var.vm_size
  priority            = var.spot_enabled ? "Spot" : "Regular"
  eviction_policy     = var.spot_enabled ? "Deallocate" : null
  max_bid_price       = var.spot_enabled ? var.spot_max_price : null

  admin_username = "azureuser"

  network_interface_ids = [
    azurerm_network_interface.zap_nic.id,
  ]

  admin_ssh_key {
    username   = "azureuser"
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  custom_data = local.custom_data

  tags = local.common_tags
}
