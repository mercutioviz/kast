# AWS Infrastructure for OWASP ZAP Cloud Scanning
# Creates ephemeral infrastructure for running ZAP in Docker

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
  # Credentials automatically resolved via:
  # 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
  # 2. AWS CLI credentials (~/.aws/credentials)
  # 3. IAM instance profiles (if running on EC2)
  # 4. ECS task roles (if running in ECS)
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

# VPC
resource "aws_vpc" "zap_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${local.scan_identifier}-vpc"
  })
}

# Internet Gateway
resource "aws_internet_gateway" "zap_igw" {
  vpc_id = aws_vpc.zap_vpc.id

  tags = merge(local.common_tags, {
    Name = "${local.scan_identifier}-igw"
  })
}

# Public Subnet
resource "aws_subnet" "zap_subnet" {
  vpc_id                  = aws_vpc.zap_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = data.aws_availability_zones.available.names[0]

  tags = merge(local.common_tags, {
    Name = "${local.scan_identifier}-subnet"
  })
}

# Route Table
resource "aws_route_table" "zap_rt" {
  vpc_id = aws_vpc.zap_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.zap_igw.id
  }

  tags = merge(local.common_tags, {
    Name = "${local.scan_identifier}-rt"
  })
}

# Route Table Association
resource "aws_route_table_association" "zap_rta" {
  subnet_id      = aws_subnet.zap_subnet.id
  route_table_id = aws_route_table.zap_rt.id
}

# Security Group
resource "aws_security_group" "zap_sg" {
  name        = "${local.scan_identifier}-sg"
  description = "Security group for KAST ZAP scanner"
  vpc_id      = aws_vpc.zap_vpc.id

  # SSH access (restricted to specific IP if needed)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # TODO: Restrict to operator IP
    description = "SSH access"
  }

  # ZAP API access
  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # TODO: Restrict to operator IP
    description = "ZAP API access"
  }

  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = merge(local.common_tags, {
    Name = "${local.scan_identifier}-sg"
  })
}

# SSH Key Pair
resource "aws_key_pair" "zap_key" {
  key_name   = "${local.scan_identifier}-key"
  public_key = var.ssh_public_key

  tags = merge(local.common_tags, {
    Name = "${local.scan_identifier}-key"
  })
}

# Get latest Ubuntu AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Get available zones
data "aws_availability_zones" "available" {
  state = "available"
}

# User data script to install Docker and run ZAP
locals {
  user_data = <<-EOF
    #!/bin/bash
    set -e
    
    # Log all output
    exec > >(tee -a /var/log/zap-setup.log)
    exec 2>&1
    
    echo "Starting ZAP cloud setup at $(date)"
    
    # Update system
    echo "Updating system packages..."
    apt-get update
    apt-get upgrade -y
    
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
    
    echo "Docker version: $(docker --version)"
    
    # Start Docker service
    echo "Starting Docker service..."
    systemctl start docker
    systemctl enable docker
    
    # Add ubuntu user to docker group for non-root access
    usermod -aG docker ubuntu
    
    # Create directories for ZAP
    echo "Creating ZAP directories..."
    mkdir -p /opt/zap/{config,reports}
    chmod -R 777 /opt/zap
    
    # Pull ZAP Docker image
    echo "Pulling ZAP Docker image: ${var.zap_docker_image}"
    docker pull ${var.zap_docker_image}
    
    # Start ZAP container with API-only configuration
    echo "Starting ZAP container..."
    docker run -d \
      --name kast-zap \
      --restart unless-stopped \
      -u zap \
      -p 8080:8080 \
      -v /opt/zap/reports:/zap/reports:rw \
      -e TZ=UTC \
      --health-cmd="curl -f http://localhost:8080/JSON/core/view/version/?apikey=${var.zap_api_key} || exit 1" \
      --health-interval=30s \
      --health-timeout=10s \
      --health-retries=3 \
      --health-start-period=60s \
      ${var.zap_docker_image} \
      zap.sh -daemon \
      -host 0.0.0.0 \
      -port 8080 \
      -config api.key=${var.zap_api_key} \
      -config api.addrs.addr.name=.* \
      -config api.addrs.addr.regex=true \
      -config api.disablekey=false \
      -config proxy.ip=127.0.0.1 \
      -config proxy.port=8081
    
    # Wait for ZAP to be ready
    echo "Waiting for ZAP to start..."
    for i in {1..30}; do
      if docker exec kast-zap curl -f http://localhost:8080/JSON/core/view/version/?apikey=${var.zap_api_key} >/dev/null 2>&1; then
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
    
    echo "ZAP cloud setup completed at $(date)"
    echo "ZAP API URL: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
    echo "ZAP API Key: ${var.zap_api_key}"
  EOF
}

# EC2 Spot Instance Request
resource "aws_spot_instance_request" "zap_instance" {
  ami                    = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.zap_subnet.id
  vpc_security_group_ids = [aws_security_group.zap_sg.id]
  key_name               = aws_key_pair.zap_key.key_name
  
  spot_price           = var.spot_max_price
  wait_for_fulfillment = true
  spot_type            = "one-time"
  
  user_data = local.user_data

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    delete_on_termination = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.scan_identifier}-instance"
  })
}

# Note: Using ephemeral public IP (auto-assigned via subnet)
# This avoids AWS Elastic IP quota limits
