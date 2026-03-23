# Deploy AIGuard on Azure Virtual Machine

Deploy AIGuard as a standalone proxy on an Azure VM.

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- Logged in: `az login`
- An active Azure subscription

## Quick Start

```bash
cd deployments/azure
chmod +x deploy.sh
./deploy.sh
```

This will:

1. Create a resource group (`aiguard-rg`)
2. Provision an Ubuntu 24.04 LTS VM (`Standard_B1s`)
3. Run cloud-init to install Python, AIGuard, and configure systemd
4. Open port 8080 in the network security group
5. Print the public IP and connection details

## Options

| Flag | Default | Description |
|---|---|---|
| `--resource-group` | `aiguard-rg` | Azure resource group name |
| `--location` | `eastus` | Azure region |
| `--vm-name` | `aiguard-vm` | Virtual machine name |
| `--vm-size` | `Standard_B1s` | VM size (SKU) |

```bash
# Example: larger VM in West Europe
./deploy.sh --vm-size Standard_B2s --location westeurope
```

## Post-Deployment

### Connect

```bash
ssh azureuser@<PUBLIC_IP>
```

### Check status

```bash
sudo systemctl status aiguard
sudo journalctl -u aiguard -f
```

### Configure your AI tools

```bash
export ANTHROPIC_BASE_URL=http://<PUBLIC_IP>:8080/anthropic
export OPENAI_BASE_URL=http://<PUBLIC_IP>:8080/openai
```

### Admin API key

The deploy script auto-generates an admin key. Retrieve it from the VM:

```bash
ssh azureuser@<PUBLIC_IP> "cat /home/aiguard/aiguard/.env | grep ADMIN"
```

## Production Hardening

For production use, consider:

- **HTTPS** — Use Azure Application Gateway or nginx with TLS
- **NSG rules** — Restrict inbound CIDRs to your team's IP ranges
- **Database** — Switch `GUARD_DATABASE_URL` to Azure Database for PostgreSQL
- **VM size** — `Standard_B2s` or larger for sustained workloads
- **Monitoring** — Export OTLP metrics to Azure Monitor or Application Insights

## Teardown

```bash
# Delete everything in one command
az group delete --name aiguard-rg --yes --no-wait
```
