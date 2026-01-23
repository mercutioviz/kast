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

# User data script to install Docker, nginx, and run ZAP
locals {
  custom_data = base64encode(<<-EOF
#!/bin/bash
set -e

# Log all output
exec > >(tee -a /var/log/zap-setup.log)
exec 2>&1

echo "Starting ZAP cloud setup at $$(date)"

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Create swap file for memory-intensive ZAP operations
echo "Configuring swap file..."
if ! swapon --show | grep -q '/swapfile'; then
    echo "Creating 4GB swap file..."
    
    # Check available disk space
    available_space=$$(df / | awk 'NR==2 {print int($$4/1024/1024)}')
    if [ $$available_space -lt 5 ]; then
        echo "WARNING: Insufficient disk space for swap file (available: $${available_space}GB)"
    else
        # Create swap file
        if ! fallocate -l 4G /swapfile 2>/dev/null; then
            echo "fallocate failed, using dd instead..."
            dd if=/dev/zero of=/swapfile bs=1G count=4 status=progress
        fi
        
        # Set correct permissions
        chmod 600 /swapfile
        
        # Set up swap area
        mkswap /swapfile
        
        # Enable swap
        swapon /swapfile
        
        # Add to /etc/fstab for persistence
        if ! grep -q "/swapfile" /etc/fstab; then
            echo "/swapfile none swap sw 0 0" >> /etc/fstab
        fi
        
        echo "Swap file created and enabled:"
        swapon --show
    fi
else
    echo "Swap already configured, skipping"
    swapon --show
fi

# Install Docker using official installation script (more reliable)
echo "Installing Docker using official script..."
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sh /tmp/get-docker.sh
rm /tmp/get-docker.sh

# Verify Docker installation
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker installation failed"
    exit 1
fi

echo "Docker version: $$(docker --version)"

# Start Docker service
echo "Starting Docker service..."
systemctl start docker
systemctl enable docker

# Add azureuser to docker group for non-root access
usermod -aG docker azureuser

# Install nginx for reverse proxy
echo "Installing nginx..."
apt-get install -y nginx

# Create nginx configuration for ZAP reverse proxy
# Configuration based on kast/config/nginx/zap-proxy.conf
echo "Configuring nginx reverse proxy..."
cat > /etc/nginx/sites-available/zap-proxy << 'NGINX_EOF'
# NGINX Reverse Proxy Configuration for OWASP ZAP
# Auto-generated by KAST Terraform (Azure)
# Based on: kast/config/nginx/zap-proxy.conf

server {
    listen 8080;
    server_name _;

    # Logging (optional - disable for production if needed)
    access_log /var/log/nginx/zap-access.log;
    error_log /var/log/nginx/zap-error.log;

    location / {
        # Proxy to ZAP on internal port
        proxy_pass http://localhost:8081;

        # Force HTTP/1.1 for better compatibility
        proxy_http_version 1.1;

        # Clear connection header to prevent connection reuse issues
        proxy_set_header Connection "";

        # CRITICAL: Rewrite Host header with port to avoid ZAP proxy loop
        # ZAP requires the port number to distinguish API requests from proxy requests
        # Without this, ZAP may treat API calls as proxy requests, causing failures
        proxy_set_header Host localhost:8081;

        # Make requests appear strictly local to ZAP
        # This prevents ZAP from treating external IPs as proxy targets
        proxy_set_header X-Real-IP 127.0.0.1;
        proxy_set_header X-Forwarded-For 127.0.0.1;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header X-Forwarded-Host localhost;

        # Increase timeouts for long-running ZAP operations
        # ZAP scans can take minutes to hours depending on target complexity
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;

        # Allow large request bodies for scan configurations and file uploads
        client_max_body_size 10M;

        # Disable buffering for better streaming of scan progress
        # This allows real-time progress updates via ZAP API
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
NGINX_EOF

# Enable the site
ln -sf /etc/nginx/sites-available/zap-proxy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
nginx -t

# Start and enable nginx
systemctl start nginx
systemctl enable nginx

echo "Nginx configured and started"

# Create directories for ZAP
echo "Creating ZAP directories..."
mkdir -p /opt/zap/{config,reports}
chmod -R 777 /opt/zap

# Pull ZAP Docker image
echo "Pulling ZAP Docker image: ${var.zap_docker_image}"
docker pull ${var.zap_docker_image}

# Start ZAP container on internal port 8081 (nginx will proxy to it)
echo "Starting ZAP container on internal port 8081..."
docker run -d \
  --name kast-zap \
  --restart unless-stopped \
  -u zap \
  -p 127.0.0.1:8081:8081 \
  -v /opt/zap/reports:/zap/reports:rw \
  -e TZ=UTC \
  --health-cmd="curl -f http://localhost:8081/JSON/core/view/version/?apikey=${var.zap_api_key} || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=60s \
  ${var.zap_docker_image} \
  zap.sh -daemon \
  -host 0.0.0.0 \
  -port 8081 \
  -config api.key=${var.zap_api_key} \
  -config api.addrs.addr.name=.* \
  -config api.addrs.addr.regex=true \
  -config api.disablekey=false

# Wait for ZAP to be ready
echo "Waiting for ZAP to start..."
for i in {1..30}; do
  if docker exec kast-zap curl -f http://localhost:8081/JSON/core/view/version/?apikey=${var.zap_api_key} >/dev/null 2>&1; then
    echo "ZAP is ready!"
    break
  fi
  echo "Waiting for ZAP... ($i/30)"
  sleep 10
done

# Verify container is running
if docker ps | grep -q kast-zap; then
  echo "ZAP container is running successfully"
  docker ps --filter name=kast-zap --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
else
  echo "ERROR: ZAP container failed to start"
  docker logs kast-zap
  exit 1
fi

# Create ready flag
touch /tmp/zap-ready

echo "ZAP cloud setup completed at $$(date)"
echo "ZAP API URL: http://$$(curl -s -H Metadata:true 'http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/publicIpAddress?api-version=2021-02-01&format=text'):8080"
echo "ZAP API Key: ${var.zap_api_key}"
  EOF
  )
}

# Virtual Machine (Spot Instance)
resource "azurerm_linux_virtual_machine" "zap_vm" {
  name                = "${local.scan_identifier}-vm"
  location            = azurerm_resource_group.zap_rg.location
  resource_group_name = azurerm_resource_group.zap_rg.name
  size                = var.vm_size
  priority            = var.use_spot_instance ? "Spot" : "Regular"
  eviction_policy     = var.use_spot_instance ? "Deallocate" : null
  max_bid_price       = var.use_spot_instance ? var.spot_max_price : null

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
