#!/usr/bin/env node

/**
 * postinstall.js — Creates a self-contained Python virtual environment
 * and installs the aigate PyPI package into it.
 *
 * Requirements: Python 3.11+ must be available on the system.
 */

const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const PACKAGE_DIR = __dirname;
const VENV_DIR = path.join(PACKAGE_DIR, ".venv");
const IS_WIN = process.platform === "win32";
const MIN_PYTHON = [3, 11];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function findPython() {
  const candidates = IS_WIN
    ? ["python", "python3", "py -3"]
    : ["python3", "python"];

  for (const cmd of candidates) {
    try {
      const version = execSync(`${cmd} --version 2>&1`, {
        encoding: "utf-8",
      }).trim();

      const match = version.match(/Python (\d+)\.(\d+)\.(\d+)/);
      if (!match) continue;

      const major = parseInt(match[1], 10);
      const minor = parseInt(match[2], 10);

      if (
        major > MIN_PYTHON[0] ||
        (major === MIN_PYTHON[0] && minor >= MIN_PYTHON[1])
      ) {
        return { cmd, version: `${major}.${minor}.${match[3]}` };
      }
    } catch {
      // not found — try next
    }
  }
  return null;
}

function venvBin(name) {
  return IS_WIN
    ? path.join(VENV_DIR, "Scripts", `${name}.exe`)
    : path.join(VENV_DIR, "bin", name);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  console.log("\n🛡️  AIGate — installing Python backend …\n");

  // 1. Locate Python
  const py = findPython();
  if (!py) {
    console.error(
      `\n❌  Python ${MIN_PYTHON.join(".")}+ is required but was not found on your PATH.\n` +
        `   Install it from https://www.python.org/downloads/ and try again.\n`
    );
    process.exit(1);
  }
  console.log(`   Found ${py.cmd} (${py.version})`);

  // 2. Create virtual environment (skip if already present and valid)
  const venvPython = venvBin("python");
  if (!fs.existsSync(venvPython)) {
    console.log("   Creating virtual environment …");
    execSync(`${py.cmd} -m venv "${VENV_DIR}"`, {
      stdio: "inherit",
      cwd: PACKAGE_DIR,
    });
  } else {
    console.log("   Virtual environment already exists");
  }

  // 3. Upgrade pip silently then install aigate
  const pip = venvBin("pip");
  console.log("   Upgrading pip …");
  execSync(`"${pip}" install --upgrade pip --quiet`, {
    stdio: "inherit",
    cwd: PACKAGE_DIR,
  });

  console.log("   Installing aigate from PyPI …");
  execSync(`"${pip}" install --upgrade aigate`, {
    stdio: "inherit",
    cwd: PACKAGE_DIR,
  });

  // 4. Verify installation
  const aigateBin = venvBin("aigate");
  if (fs.existsSync(aigateBin)) {
    console.log("\n✅  AIGate installed successfully!");
    console.log(
      "   Run `aigate --help` to get started.\n"
    );
  } else {
    console.error(
      "\n⚠️  Installation completed but the aigate binary was not found."
    );
    console.error("   Try running: pip install aigate\n");
    process.exit(1);
  }
}

main();
