// ─────────────────────────────────────────────────────────────────────────────
// AIGuard — Azure Bicep Template
//
// Deploys a VM with cloud-init that installs AIGuard from the public repo
// and starts the proxy as a systemd service.
// ─────────────────────────────────────────────────────────────────────────────

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Name of the virtual machine')
param vmName string = 'aiguard-vm'

@description('VM size (Standard_B1s = free tier eligible)')
@allowed([
  'Standard_B1s'
  'Standard_B1ls'
  'Standard_B2s'
  'Standard_B2ats_v2'
  'Standard_DS1_v2'
])
param vmSize string = 'Standard_B1s'

@description('Admin username for the VM')
param adminUsername string = 'azureuser'

@description('SSH public key for authentication')
@secure()
param sshPublicKey string

@description('AIGuard GitHub repo URL')
param repoUrl string = 'https://github.com/aibuildspace/aiguard.git'

@description('Git branch or tag to deploy')
param repoBranch string = 'main'

// ── Variables ───────────────────────────────────────────────────────────────
var prefix = 'aiguard'
var vnetName = '${prefix}-vnet'
var subnetName = '${prefix}-subnet'
var nsgName = '${prefix}-nsg'
var nicName = '${prefix}-nic'
var publicIpName = '${prefix}-pip'

var cloudInitScript = format('''
#cloud-config
package_update: true
package_upgrade: true

packages:
  - python3-pip
  - python3-venv
  - git

runcmd:
  # Create service user
  - useradd -r -m -s /bin/bash aiguard

  # Clone repo and install
  - su - aiguard -c "git clone --depth 1 --branch {0} {1} ~/repo"
  - su - aiguard -c "cd ~/repo && python3 -m pip install --user --break-system-packages ."
  - su - aiguard -c "mkdir -p ~/aiguard"

  # Generate config with admin key
  - |
    ADMIN_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    cat > /home/aiguard/aiguard/.env <<EOF
    GUARD_HOST=0.0.0.0
    GUARD_PORT=8080
    GUARD_LOG_LEVEL=info
    GUARD_PASSTHROUGH_MODE=true
    GUARD_ADMIN_API_ENABLED=true
    GUARD_ADMIN_API_KEY=$ADMIN_KEY
    GUARD_DATABASE_URL=sqlite+aiosqlite:///./aiguard.db
    EOF
    chown aiguard:aiguard /home/aiguard/aiguard/.env
    sed -i 's/^[[:space:]]*//' /home/aiguard/aiguard/.env

  # Copy shields into working directory
  - su - aiguard -c "cp -r ~/repo/shields ~/aiguard/shields"

  # Create systemd service
  - |
    cat > /etc/systemd/system/aiguard.service <<EOF
    [Unit]
    Description=AIGuard LLM Security Proxy
    After=network.target

    [Service]
    Type=simple
    User=aiguard
    WorkingDirectory=/home/aiguard/aiguard
    ExecStart=/home/aiguard/.local/bin/guard start --host 0.0.0.0 --port 8080
    Restart=always
    RestartSec=5
    Environment=PATH=/home/aiguard/.local/bin:/usr/bin:/bin

    [Install]
    WantedBy=multi-user.target
    EOF
    sed -i 's/^[[:space:]]*//' /etc/systemd/system/aiguard.service

  - systemctl daemon-reload
  - systemctl enable aiguard
  - systemctl start aiguard
''', repoBranch, repoUrl)

// ── Network Security Group ──────────────────────────────────────────────────
resource nsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowSSH'
        properties: {
          priority: 1000
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowAIGuard'
        properties: {
          priority: 1010
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '8080'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// ── Virtual Network ─────────────────────────────────────────────────────────
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
    subnets: [
      {
        name: subnetName
        properties: {
          addressPrefix: '10.0.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}

// ── Public IP ───────────────────────────────────────────────────────────────
resource publicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: publicIpName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

// ── Network Interface ───────────────────────────────────────────────────────
resource nic 'Microsoft.Network/networkInterfaces@2023-11-01' = {
  name: nicName
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: vnet.properties.subnets[0].id
          }
          publicIPAddress: {
            id: publicIp.id
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

// ── Virtual Machine ─────────────────────────────────────────────────────────
resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: vmName
  location: location
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      customData: base64(cloudInitScript)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Standard_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────
output publicIpAddress string = publicIp.properties.ipAddress
output sshCommand string = 'ssh ${adminUsername}@${publicIp.properties.ipAddress}'
output proxyUrl string = 'http://${publicIp.properties.ipAddress}:8080'
output portalUrl string = 'http://${publicIp.properties.ipAddress}:8080/portal'
