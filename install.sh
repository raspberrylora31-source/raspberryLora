#!/bin/bash

################################################################################
# Automated Installation Script for Real-Time Detection System
# Raspberry Pi 4B Setup
# 
# Usage: bash install.sh
################################################################################

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/home/lora/raspberryLora"
PYTHON_VERSION="python3.9"
VENV_DIR="$PROJECT_DIR/venv"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

################################################################################
# Checks
################################################################################

check_os() {
    print_header "Checking Operating System"
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        print_success "Linux detected"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        print_error "macOS detected. This script is for Raspberry Pi (Linux) only."
        exit 1
    else
        print_error "Unsupported OS: $OSTYPE"
        exit 1
    fi
}

check_python() {
    print_header "Checking Python Installation"
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found"
        print_info "Installing Python 3..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
    else
        version=$(python3 --version)
        print_success "$version found"
    fi
}

check_git() {
    print_header "Checking Git Installation"
    
    if ! command -v git &> /dev/null; then
        print_warning "Git not found, installing..."
        sudo apt-get install -y git
    else
        print_success "Git found: $(git --version)"
    fi
}

################################################################################
# System Dependencies
################################################################################

install_system_deps() {
    print_header "Installing System Dependencies"
    
    print_info "Updating package lists..."
    sudo apt-get update -qq
    
    print_info "Installing required packages..."
    sudo apt-get install -y \
        python3-pip \
        python3-dev \
        python3-venv \
        libatlas-base-dev \
        libjasper-dev \
        libtiff5 \
        libjasper1 \
        libharfbuzz0b \
        libwebp6 \
        libopenjp2-7 \
        git \
        curl \
        wget \
        build-essential \
        2>&1 | grep -E "^(Setting|Processing|Unpacking)" || true
    
    print_success "System dependencies installed"
}

################################################################################
# UART Configuration
################################################################################

configure_uart() {
    print_header "Configuring UART for ESP32"
    
    # Detect which config file to use
    if [[ -f "/boot/firmware/config.txt" ]]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    elif [[ -f "/boot/config.txt" ]]; then
        CONFIG_FILE="/boot/config.txt"
    else
        print_error "Could not find boot config file"
        return 1
    fi
    
    # Check if UART already enabled
    if grep -q "enable_uart=1" "$CONFIG_FILE"; then
        print_warning "UART already enabled"
    else
        print_info "Enabling UART in $CONFIG_FILE..."
        
        # Backup config file
        sudo cp "$CONFIG_FILE" "$CONFIG_FILE.backup"
        print_success "Backed up to $CONFIG_FILE.backup"
        
        # Add UART configuration
        echo "" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "# UART for ESP32 LoRa communication" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "enable_uart=1" | sudo tee -a "$CONFIG_FILE" > /dev/null
        
        print_success "UART enabled"
        print_warning "REBOOT REQUIRED to apply UART changes"
    fi
}

################################################################################
# Virtual Environment
################################################################################

setup_venv() {
    print_header "Setting Up Python Virtual Environment"
    
    if [[ -d "$VENV_DIR" ]]; then
        print_warning "Virtual environment already exists at $VENV_DIR"
        print_info "Recreating environment..."
        rm -rf "$VENV_DIR"
    fi
    
    print_info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    print_success "Virtual environment created"
    
    # Activate venv
    source "$VENV_DIR/bin/activate"
    print_success "Virtual environment activated"
    
    # Upgrade pip
    print_info "Upgrading pip..."
    pip install --upgrade pip setuptools wheel -q
    print_success "pip upgraded"
}

################################################################################
# Python Dependencies
################################################################################

install_python_deps() {
    print_header "Installing Python Dependencies"
    
    source "$VENV_DIR/bin/activate"
    
    if [[ ! -f "$PROJECT_DIR/requirements.txt" ]]; then
        print_error "requirements.txt not found"
        return 1
    fi
    
    print_info "Installing dependencies from requirements.txt..."
    print_warning "This may take 10-15 minutes on Raspberry Pi..."
    
    pip install -q -r "$PROJECT_DIR/requirements.txt"
    
    print_success "Python dependencies installed"
}

################################################################################
# Test Installation
################################################################################

test_installation() {
    print_header "Testing Installation"
    
    source "$VENV_DIR/bin/activate"
    
    # Test imports
    print_info "Testing module imports..."
    python3 << 'EOF'
import cv2
print(f"OpenCV version: {cv2.__version__}")

import torch
print(f"PyTorch version: {torch.__version__}")

import serial
print("pyserial: OK")

import numpy
print(f"NumPy version: {numpy.__version__}")

print("\n✓ All imports successful!")
EOF
    
    # Test camera detection
    print_info "Testing camera detection..."
    python3 << 'EOF'
import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("✓ Camera detected at /dev/video0")
    ret, frame = cap.read()
    if ret:
        print(f"✓ Frame captured: {frame.shape}")
    cap.release()
else:
    print("⚠ Camera not found at /dev/video0 (this may be normal)")
EOF
    
    # Test serial ports
    print_info "Testing serial ports..."
    python3 << 'EOF'
from lora.serial_handler import SerialHandler
ports = SerialHandler.find_serial_ports()
if ports:
    print(f"✓ Serial ports found: {ports}")
else:
    print("ℹ No serial ports found (ESP32 may not be connected)")
EOF
}

################################################################################
# Create Systemd Service
################################################################################

create_service() {
    print_header "Setting Up Systemd Service (Optional)"
    
    read -p "Create systemd service for auto-start? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        return
    fi
    
    SERVICE_FILE="/etc/systemd/system/detection.service"
    
    print_info "Creating systemd service file..."
    
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Real-Time Object Detection System
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_DIR/bin/python3 $PROJECT_DIR/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "Service file created at $SERVICE_FILE"
    
    # Reload systemd
    sudo systemctl daemon-reload
    print_success "Systemd reloaded"
    
    read -p "Enable service for auto-start on boot? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl enable detection.service
        print_success "Service enabled for auto-start"
    fi
}

################################################################################
# Create Startup Script
################################################################################

create_startup_script() {
    print_header "Creating Startup Script"
    
    STARTUP_SCRIPT="$PROJECT_DIR/run.sh"
    
    cat > "$STARTUP_SCRIPT" << 'EOF'
#!/bin/bash
# Startup script for detection system

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Change to project directory
cd "$PROJECT_DIR"

# Run with provided arguments, or use defaults
if [[ $# -eq 0 ]]; then
    python3 main.py
else
    python3 main.py "$@"
fi
EOF
    
    chmod +x "$STARTUP_SCRIPT"
    print_success "Startup script created: $STARTUP_SCRIPT"
    print_info "Usage: bash run.sh [options]"
}

################################################################################
# Configuration
################################################################################

create_env_file() {
    print_header "Creating Configuration File"
    
    ENV_FILE="$PROJECT_DIR/.env"
    
    if [[ -f "$ENV_FILE" ]]; then
        print_warning ".env file already exists"
        read -p "Overwrite? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return
        fi
    fi
    
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    print_success "Configuration file created: $ENV_FILE"
    print_info "Edit this file to customize settings"
}

################################################################################
# Summary
################################################################################

print_summary() {
    print_header "Installation Summary"
    
    echo -e "\n${GREEN}Installation completed successfully!${NC}\n"
    
    echo "📍 Project Location: $PROJECT_DIR"
    echo "🐍 Virtual Environment: $VENV_DIR"
    echo ""
    
    echo -e "${BLUE}Quick Start:${NC}"
    echo "  cd $PROJECT_DIR"
    echo "  source venv/bin/activate"
    echo "  python3 main.py --help"
    echo "  python3 main.py"
    echo ""
    
    echo -e "${BLUE}Or use startup script:${NC}"
    echo "  bash $PROJECT_DIR/run.sh"
    echo ""
    
    echo -e "${BLUE}System Service:${NC}"
    echo "  sudo systemctl status detection.service"
    echo "  sudo systemctl start detection.service"
    echo "  sudo systemctl stop detection.service"
    echo ""
    
    echo -e "${BLUE}Documentation:${NC}"
    echo "  README.md - Full documentation"
    echo "  QUICKSTART.md - Quick start guide"
    echo "  WIRING_GUIDE.md - Hardware wiring"
    echo "  OPTIMIZATION_GUIDE.md - Performance tuning"
    echo ""
    
    if [[ -f "/boot/firmware/config.txt" ]] || [[ -f "/boot/config.txt" ]]; then
        if grep -q "enable_uart=1" "/boot/firmware/config.txt" 2>/dev/null || grep -q "enable_uart=1" "/boot/config.txt" 2>/dev/null; then
            print_success "UART is enabled"
        else
            print_warning "UART may need to be enabled (see configuration step)"
        fi
    fi
    
    echo ""
}

################################################################################
# Main Installation Flow
################################################################################

main() {
    clear
    print_header "Real-Time Detection System - Installation Script"
    echo "Raspberry Pi 4B Setup"
    echo ""
    
    # Check requirements
    check_os
    check_python
    check_git
    
    # Install dependencies
    install_system_deps
    
    # Configure UART
    configure_uart
    
    # Setup Python environment
    setup_venv
    install_python_deps
    
    # Test installation
    test_installation
    
    # Optional configurations
    create_env_file
    create_startup_script
    create_service
    
    # Print summary
    print_summary
    
    print_info "Installation script completed!"
    echo ""
}

# Run main function
main "$@"
