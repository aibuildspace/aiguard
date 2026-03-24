# AIGate — npm installer

Install **AIGate** globally via npm. This package bootstraps a self-contained Python virtual environment and installs the [aigate](https://pypi.org/project/aigate/) PyPI package automatically.

## Prerequisites

- **Node.js** 16+
- **Python** 3.11+ (must be on your `PATH`)

## Install

```bash
npm install -g aigate
```

## Usage

```bash
# Start the proxy server
aigate start

# Or use the full command name
aigate server start

# Interactive onboarding wizard
aigate onboard

# View all commands
aigate --help
```

## How it works

1. `npm install -g aigate` downloads this wrapper package
2. The `postinstall` script locates Python 3.11+ on your system
3. A virtual environment is created inside the npm package directory
4. The `aigate` Python package is installed from PyPI into that venv
5. The `aigate` command delegates to the Python CLI

No global Python packages are modified — everything stays isolated in the venv.

## Upgrade

```bash
npm update -g aigate
```

## Uninstall

```bash
npm uninstall -g aigate
```

This removes the package and its bundled virtual environment.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Python 3.11+ is required` | Install Python 3.11+ and ensure `python3` is on your PATH |
| `aigate binary not found` after install | Run `npm rebuild aigate` |
| Permission errors on Linux | Avoid `sudo npm install -g`; configure npm prefix instead: `npm config set prefix ~/.npm-global` |

## Publishing (maintainers)

```bash
cd deployments/npm
# Bump version in package.json to match pyproject.toml
npm publish
```
