// server/src/wfpack_signer.js
// Workflow Package Signing and Verification System
import crypto from "crypto";
import nacl from "tweetnacl";

/**
 * Generate a new ed25519 key pair for a publisher
 */
export function generateKeyPair() {
  const keyPair = nacl.sign.keyPair();
  return {
    publicKey: Buffer.from(keyPair.publicKey).toString('base64'),
    secretKey: Buffer.from(keyPair.secretKey).toString('base64')
  };
}

/**
 * Sign a workflow package with ed25519
 * @param {Buffer} packageBytes - The complete package bytes
 * @param {string} secretKeyBase64 - Publisher's secret key (base64)
 * @returns {string} Base64 encoded signature
 */
export function signPackage(packageBytes, secretKeyBase64) {
  // Calculate SHA256 hash of the package
  const hash = crypto.createHash('sha256').update(packageBytes).digest();

  // Convert base64 secret key to Uint8Array
  const secretKey = Buffer.from(secretKeyBase64, 'base64');

  // Sign the hash
  const signature = nacl.sign.detached(hash, secretKey);

  return Buffer.from(signature).toString('base64');
}

/**
 * Verify a workflow package signature
 * @param {Buffer} packageBytes - The complete package bytes
 * @param {string} signatureBase64 - Base64 encoded signature
 * @param {string} publicKeyBase64 - Publisher's public key (base64)
 * @returns {boolean} True if signature is valid
 */
export function verifyPackage(packageBytes, signatureBase64, publicKeyBase64) {
  try {
    // Calculate SHA256 hash of the package
    const hash = crypto.createHash('sha256').update(packageBytes).digest();

    // Convert base64 values to Uint8Arrays
    const signature = Buffer.from(signatureBase64, 'base64');
    const publicKey = Buffer.from(publicKeyBase64, 'base64');

    // Verify the signature
    return nacl.sign.detached.verify(hash, signature, publicKey);
  } catch (error) {
    console.error('Package verification error:', error);
    return false;
  }
}

/**
 * Calculate SHA256 hash of package bytes
 * @param {Buffer} packageBytes - The complete package bytes
 * @returns {string} Hex encoded hash
 */
export function calculateHash(packageBytes) {
  return crypto.createHash('sha256').update(packageBytes).digest('hex');
}

/**
 * Validate workflow package manifest
 * @param {Object} manifest - Parsed manifest.json
 * @returns {Object} Validation result with errors
 */
export function validateManifest(manifest) {
  const errors = [];

  // Required fields
  const requiredFields = ['key', 'name', 'version', 'publisher', 'engine', 'workflows'];
  for (const field of requiredFields) {
    if (!manifest[field]) {
      errors.push(`Missing required field: ${field}`);
    }
  }

  // Validate publisher info
  if (manifest.publisher) {
    if (!manifest.publisher.id) {
      errors.push('Missing publisher.id');
    }
    if (!manifest.publisher.pubkey_ed25519) {
      errors.push('Missing publisher.pubkey_ed25519');
    }
  }

  // Validate engine version constraints
  if (manifest.engine) {
    if (!manifest.engine.min) {
      errors.push('Missing engine.min version');
    }
    if (manifest.engine.min && !isValidSemver(manifest.engine.min)) {
      errors.push('Invalid engine.min version format');
    }
  }

  // Validate version
  if (manifest.version && !isValidSemver(manifest.version)) {
    errors.push('Invalid version format (must be semver)');
  }

  // Validate workflows
  if (manifest.workflows) {
    if (!Array.isArray(manifest.workflows)) {
      errors.push('workflows must be an array');
    } else {
      let hasEntry = false;
      for (const workflow of manifest.workflows) {
        if (!workflow.file) {
          errors.push('workflow missing file path');
        }
        if (workflow.entry) {
          hasEntry = true;
        }
      }
      if (!hasEntry) {
        errors.push('At least one workflow must be marked as entry point');
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Simple semver validation
 * @param {string} version - Version string to validate
 * @returns {boolean} True if valid semver
 */
function isValidSemver(version) {
  const semverRegex = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$/;
  return semverRegex.test(version);
}

/**
 * Check if a version satisfies engine constraints
 * @param {string} engineVersion - Current engine version
 * @param {string} minVersion - Minimum required version
 * @param {string} maxVersion - Maximum supported version (optional)
 * @returns {boolean} True if compatible
 */
export function checkEngineCompatibility(engineVersion, minVersion, maxVersion = null) {
  try {
    const current = parseVersion(engineVersion);
    const min = parseVersion(minVersion);

    // Check minimum version
    if (compareVersions(current, min) < 0) {
      return false;
    }

    // Check maximum version if specified
    if (maxVersion) {
      const max = parseVersion(maxVersion);
      if (compareVersions(current, max) > 0) {
        return false;
      }
    }

    return true;
  } catch (error) {
    console.error('Version compatibility check error:', error);
    return false;
  }
}

/**
 * Parse semver string into comparable object
 * @param {string} version - Version string
 * @returns {Object} Parsed version components
 */
function parseVersion(version) {
  const parts = version.replace(/^v/, '').split('.');
  return {
    major: parseInt(parts[0]) || 0,
    minor: parseInt(parts[1]) || 0,
    patch: parseInt(parts[2]) || 0
  };
}

/**
 * Compare two version objects
 * @param {Object} a - First version
 * @param {Object} b - Second version
 * @returns {number} -1, 0, or 1
 */
function compareVersions(a, b) {
  if (a.major !== b.major) return a.major - b.major;
  if (a.minor !== b.minor) return a.minor - b.minor;
  return a.patch - b.patch;
}

/**
 * Create a sample manifest for testing
 * @param {string} key - Workflow key
 * @param {Object} publisher - Publisher info
 * @returns {Object} Sample manifest
 */
export function createSampleManifest(key, publisher) {
  return {
    key,
    name: `Sample Workflow: ${key}`,
    version: "1.0.0",
    publisher: {
      id: publisher.id,
      name: publisher.name,
      pubkey_ed25519: publisher.publicKey
    },
    engine: {
      min: "0.4.0",
      max: "0.6.x"
    },
    workflows: [
      {
        file: "workflows/main.json",
        entry: true
      }
    ],
    requires: {
      adapters: ["wechat"],
      actions: ["chat.*", "ocr.*", "api.*"],
      permissions: {
        ui_automation: true,
        network: ["api_base"],
        file_access: false
      }
    },
    vars_schema: {
      app: {
        type: "string",
        enum: ["wechat", "slack"],
        default: "wechat"
      },
      input_box: {
        type: "object",
        required: ["x", "y"]
      }
    },
    post_install: {
      create_topics: ["device.${device_id}.${app}.hp.fifo"]
    }
  };
}