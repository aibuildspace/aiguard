# Deploy AIGate on Azure (Bicep)

Deploy AIGate as a standalone proxy on an Azure VM using a Bicep template.
Installs from the public repo: [github.com/aibuildspace/aigate](https://github.com/aibuildspace/aigate)

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed (includes Bicep)
- Logged in: `az login`
- An active Azure subscription

## Quick Start

```bash
cd deployments/azure
chmod +x deploy.sh
./deploy.sh
```

The interactive script will:

1. Let you pick a **region** and **VM size** (arrow keys)
2. Deploy the Bicep template (VM + networking + NSG)
3. Wait for cloud-init to install AIGate from GitHub
4. Verify the service is healthy
5. **Onboard your first user** (org -> user -> API key)
6. Print ready-to-use `export` commands for your AI tool

## Files

| File | Description |
|---|---|
| `main.bicep` | ARM/Bicep template: VM, VNet, NSG, public IP |
| `deploy.sh` | Interactive wrapper: deploys Bicep + onboards user |

## Options

| Flag | Default | Description |
|---|---|---|
| `--location` | `eastus` | Azure region |
| `--vm-size` | `Standard_B1s` | VM size (B1s = free tier eligible) |
| `--vm-name` | `aigate-vm` | Virtual machine name |
| `--resource-group` | `aigate-rg` | Resource group name |
| `--branch` | `main` | Git branch/tag to deploy from |
| `--yes`, `-y` | | Skip all prompts, use defaults |

```bash
# Non-interactive deploy
./deploy.sh --location australiaeast --vm-size Standard_B2s --yes

# Deploy a specific release
./deploy.sh --branch v0.2.0
```

## Deploy Bicep Directly

You can deploy the Bicep template without the wrapper script:

```bash
az group create --name aigate-rg --location eastus

az deployment group create \
  --resource-group aigate-rg \
  --template-file main.bicep \
  --parameters vmSize=Standard_B1s sshPublicKey="$(cat ~/.ssh/id_rsa.pub)"
```

## Post-Deployment

### Connect

```bash
ssh azureuser@<PUBLIC_IP>
```

### Check status

```bash
sudo systemctl status aigate
sudo journalctl -u aigate -f
```

### Admin API key

```bash
ssh azureuser@<PUBLIC_IP> "sudo grep ADMIN /home/aigate/aigate/.env"
```

### Manual onboarding (if skipped during deploy)

```bash
ssh azureuser@<PUBLIC_IP>
sudo -u aigate aigate onboard
```

## Production Hardening

- **HTTPS** - Use Azure Application Gateway or nginx with TLS
- **NSG rules** - Restrict inbound CIDRs to your team IP ranges
- **Database** - Switch `GUARD_DATABASE_URL` to Azure Database for PostgreSQL
- **VM size** - `Standard_B2s` or larger for sustained workloads
- **Monitoring** - Export OTLP metrics to Azure Monitor

## Teardown

```bash
az group delete --name aigate-rg --yes --no-wait
```
