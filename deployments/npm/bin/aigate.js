#!/usr/bin/env node

/**
 * bin/aigate.js — Thin wrapper that delegates all commands to the
 * Python `aigate` CLI installed in the package's virtual environment.
 *
 * Usage:
 *   aigate start          →  aigate start
 *   aigate shield list    →  aigate shield list
 *   aigate --help         →  aigate --help
 */

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const PACKAGE_DIR = path.resolve(__dirname, "..");
const VENV_DIR = path.join(PACKAGE_DIR, ".venv");
const IS_WIN = process.platform === "win32";

function venvBin(name) {
  return IS_WIN
    ? path.join(VENV_DIR, "Scripts", `${name}.exe`)
    : path.join(VENV_DIR, "bin", name);
}

// ---------------------------------------------------------------------------
// Resolve the Python aigate CLI
// ---------------------------------------------------------------------------

const aigateBin = venvBin("aigate");
const pythonBin = venvBin("python");

if (!fs.existsSync(aigateBin) && !fs.existsSync(pythonBin)) {
  console.error(
    "❌  AIGate Python environment not found.\n" +
      "   Run `npm rebuild aigate` to reinstall, or check that Python 3.11+ is available.\n"
  );
  process.exit(1);
}

// Prefer the installed `aigate` script; fall back to `python -m aigate.cli.main`
const useAigateBin = fs.existsSync(aigateBin);
const cmd = useAigateBin ? aigateBin : pythonBin;
const args = useAigateBin
  ? process.argv.slice(2)
  : ["-m", "aigate.cli.main", ...process.argv.slice(2)];

// ---------------------------------------------------------------------------
// Spawn the Python process, forwarding stdio and exit code
// ---------------------------------------------------------------------------

// Include bundled shields from python-src/ if user hasn't set their own
const bundledShieldsDir = path.join(PACKAGE_DIR, "python-src", "shields");
const shieldsEnv = process.env.GUARD_SHIELDS_DIRS
  ? process.env.GUARD_SHIELDS_DIRS
  : fs.existsSync(bundledShieldsDir)
    ? `${bundledShieldsDir}:./shields:./user_shields`
    : undefined;

const child = spawn(cmd, args, {
  stdio: "inherit",
  env: {
    ...process.env,
    // Ensure the venv's bin dir is first on PATH so sub-processes find
    // the right Python (e.g., for shield logic modules).
    PATH: `${path.dirname(aigateBin)}${path.delimiter}${process.env.PATH || ""}`,
    VIRTUAL_ENV: VENV_DIR,
    // Point to bundled shields so they are always discoverable
    ...(shieldsEnv ? { GUARD_SHIELDS_DIRS: shieldsEnv } : {}),
  },
});

child.on("error", (err) => {
  console.error(`❌  Failed to start AIGate: ${err.message}`);
  process.exit(1);
});

child.on("close", (code) => {
  process.exit(code ?? 1);
});
