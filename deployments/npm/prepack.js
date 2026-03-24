#!/usr/bin/env node

/**
 * prepack.js — Bundles the Python project source into python-src/
 * so the npm package is fully self-contained (no PyPI dependency).
 *
 * Runs automatically before `npm pack` and `npm publish`.
 */

const fs = require("fs");
const path = require("path");

const PACKAGE_DIR = __dirname;
const REPO_ROOT = path.resolve(PACKAGE_DIR, "..", "..");
const DEST = path.join(PACKAGE_DIR, "python-src");

// Directories and files to bundle from the repo root
const COPY_DIRS = ["aigate", "shields"];
const COPY_FILES = ["pyproject.toml", "README.md", "LICENSE"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function copyDirSync(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    // Skip __pycache__, .pyc, .egg-info, .venv
    if (
      entry.name === "__pycache__" ||
      entry.name.endsWith(".pyc") ||
      entry.name.endsWith(".egg-info") ||
      entry.name === ".venv"
    ) {
      continue;
    }

    if (entry.isDirectory()) {
      copyDirSync(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

console.log("📦  Bundling Python source into python-src/ …\n");

// Verify we're in the right place
if (!fs.existsSync(path.join(REPO_ROOT, "pyproject.toml"))) {
  console.error(
    "❌  Could not find pyproject.toml at repo root.\n" +
      `   Expected: ${REPO_ROOT}\n` +
      "   Make sure this script runs from within the aigate repository.\n"
  );
  process.exit(1);
}

// Clean previous bundle
if (fs.existsSync(DEST)) {
  fs.rmSync(DEST, { recursive: true });
}
fs.mkdirSync(DEST, { recursive: true });

// Copy directories
for (const dir of COPY_DIRS) {
  const src = path.join(REPO_ROOT, dir);
  if (fs.existsSync(src)) {
    console.log(`   Copying ${dir}/ …`);
    copyDirSync(src, path.join(DEST, dir));
  } else {
    console.warn(`   ⚠️  Skipping ${dir}/ (not found)`);
  }
}

// Copy files
for (const file of COPY_FILES) {
  const src = path.join(REPO_ROOT, file);
  if (fs.existsSync(src)) {
    console.log(`   Copying ${file} …`);
    fs.copyFileSync(src, path.join(DEST, file));
  } else {
    console.warn(`   ⚠️  Skipping ${file} (not found)`);
  }
}

console.log("\n✅  Python source bundled into python-src/\n");
