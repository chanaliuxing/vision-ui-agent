// server/src/marketplace.js
// Marketplace API for workflow publishing and discovery
import express from "express";
import multer from "multer";
import { authRequired } from "./middleware.js";
import { pool } from "./db.js";
import {
  generateKeyPair,
  signPackage,
  verifyPackage,
  calculateHash,
  validateManifest,
  checkEngineCompatibility,
  createSampleManifest
} from "./wfpack_signer.js";
import fs from "fs";
import path from "path";

export const marketplace = express.Router();

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    const uploadDir = './uploads/packages';
    if (!fs.existsSync(uploadDir)) {
      fs.mkdirSync(uploadDir, { recursive: true });
    }
    cb(null, uploadDir);
  },
  filename: function (req, file, cb) {
    const timestamp = Date.now();
    cb(null, `${timestamp}-${file.originalname}`);
  }
});

const upload = multer({
  storage,
  limits: {
    fileSize: 100 * 1024 * 1024 // 100MB limit
  },
  fileFilter: function (req, file, cb) {
    if (file.mimetype === 'application/gzip' || file.originalname.endsWith('.wfpack.tgz')) {
      cb(null, true);
    } else {
      cb(new Error('Only .wfpack.tgz files are allowed'));
    }
  }
});

// Publisher management
marketplace.post("/publishers", authRequired, async (req, res) => {
  try {
    const { name, contact_email } = req.body || {};
    if (!name) return res.status(400).json({ error: "name required" });

    // Generate ed25519 key pair for the publisher
    const keyPair = generateKeyPair();

    const { rows } = await pool.query(
      `insert into publishers(user_id, name, contact_email, status)
       values($1, $2, $3, 'active') returning id, name, status`,
      [req.user.user_id, name, contact_email || null]
    );

    res.json({
      publisher: rows[0],
      keys: {
        public_key: keyPair.publicKey,
        secret_key: keyPair.secretKey // In production, this should be securely delivered
      }
    });
  } catch (error) {
    console.error("Create publisher error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// List user's publishers
marketplace.get("/publishers", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      "select id, name, contact_email, status, created_at from publishers where user_id = $1",
      [req.user.user_id]
    );
    res.json({ publishers: rows });
  } catch (error) {
    console.error("List publishers error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Create marketplace listing
marketplace.post("/listings", authRequired, async (req, res) => {
  try {
    const {
      publisher_id,
      key,
      title,
      summary,
      description,
      category,
      price_cents,
      visibility
    } = req.body || {};

    if (!publisher_id || !key || !title) {
      return res.status(400).json({ error: "publisher_id, key, and title required" });
    }

    // Verify user owns the publisher
    const { rows: publishers } = await pool.query(
      "select id from publishers where id = $1 and user_id = $2",
      [publisher_id, req.user.user_id]
    );

    if (!publishers.length) {
      return res.status(403).json({ error: "publisher not found or not owned by user" });
    }

    const { rows } = await pool.query(
      `insert into marketplace_listings(publisher_id, key, title, summary, description, category, price_cents, visibility)
       values($1, $2, $3, $4, $5, $6, $7, $8) returning *`,
      [publisher_id, key, title, summary || null, description || null, category || 'Productivity', price_cents || 0, visibility || 'public']
    );

    res.json({ listing: rows[0] });
  } catch (error) {
    if (error.code === '23505') {
      return res.status(409).json({ error: "listing key already exists for this publisher" });
    }
    console.error("Create listing error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Upload package version
marketplace.post("/listings/:id/versions", authRequired, upload.single('package'), async (req, res) => {
  try {
    const listing_id = req.params.id;
    const { version, changelog, is_prerelease } = req.body || {};

    if (!req.file) {
      return res.status(400).json({ error: "package file required" });
    }

    if (!version) {
      return res.status(400).json({ error: "version required" });
    }

    // Verify user owns the listing
    const { rows: listings } = await pool.query(
      `select l.id, l.key, p.user_id
       from marketplace_listings l
       join publishers p on p.id = l.publisher_id
       where l.id = $1 and p.user_id = $2`,
      [listing_id, req.user.user_id]
    );

    if (!listings.length) {
      return res.status(403).json({ error: "listing not found or not owned by user" });
    }

    // Read and process the uploaded package
    const packageBytes = fs.readFileSync(req.file.path);
    const sha256 = calculateHash(packageBytes);

    // For demo purposes, create a mock manifest
    // In production, you would extract and parse the actual manifest from the .tgz file
    const mockPublisher = {
      id: listings[0].user_id,
      name: "Demo Publisher",
      publicKey: generateKeyPair().publicKey // Mock public key
    };

    const manifest = createSampleManifest(listings[0].key, mockPublisher);

    // Sign the package (in production, this would be done by the publisher's client)
    const mockSecretKey = generateKeyPair().secretKey;
    const signature = signPackage(packageBytes, mockSecretKey);

    // Verify the signature works
    const isValid = verifyPackage(packageBytes, signature, mockPublisher.publicKey);
    if (!isValid) {
      return res.status(400).json({ error: "package signature verification failed" });
    }

    // Validate manifest
    const validation = validateManifest(manifest);
    if (!validation.valid) {
      return res.status(400).json({ error: "invalid manifest", details: validation.errors });
    }

    // Store the package version
    const storage_url = `/packages/${req.file.filename}`;

    const { rows } = await pool.query(
      `insert into marketplace_versions(listing_id, version, engine_min, sha256, size_bytes, storage_url, manifest, signature, changelog, is_prerelease)
       values($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) returning *`,
      [
        listing_id,
        version,
        manifest.engine.min,
        sha256,
        packageBytes.length,
        storage_url,
        JSON.stringify(manifest),
        signature,
        changelog || null,
        is_prerelease === 'true'
      ]
    );

    // Update latest_version on the listing
    await pool.query(
      "update marketplace_listings set latest_version = $1 where id = $2",
      [version, listing_id]
    );

    // Clean up uploaded file (in production, move to permanent storage)
    fs.unlinkSync(req.file.path);

    res.json({ version: rows[0] });
  } catch (error) {
    // Clean up file on error
    if (req.file && fs.existsSync(req.file.path)) {
      fs.unlinkSync(req.file.path);
    }

    if (error.code === '23505') {
      return res.status(409).json({ error: "version already exists" });
    }
    console.error("Upload version error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Browse marketplace listings
marketplace.get("/browse", async (req, res) => {
  try {
    const {
      category,
      search,
      featured,
      sort = 'created_at',
      order = 'desc',
      limit = 20,
      offset = 0
    } = req.query;

    let query = `
      select l.*, p.name as publisher_name, c.name as category_name
      from marketplace_listings l
      join publishers p on p.id = l.publisher_id
      left join marketplace_categories c on c.name = l.category
      where l.visibility = 'public' and l.status = 'active'
    `;

    const params = [];
    let paramIndex = 1;

    if (category) {
      query += ` and l.category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }

    if (search) {
      query += ` and (l.title ilike $${paramIndex} or l.summary ilike $${paramIndex})`;
      params.push(`%${search}%`);
      paramIndex++;
    }

    if (featured === 'true') {
      query += ` and l.featured = true`;
    }

    // Validate sort field
    const allowedSorts = ['created_at', 'updated_at', 'title', 'download_count', 'rating_avg', 'price_cents'];
    const sortField = allowedSorts.includes(sort) ? sort : 'created_at';
    const sortOrder = order.toLowerCase() === 'asc' ? 'asc' : 'desc';

    query += ` order by l.${sortField} ${sortOrder}`;
    query += ` limit $${paramIndex} offset $${paramIndex + 1}`;
    params.push(Math.min(parseInt(limit), 100), parseInt(offset) || 0);

    const { rows } = await pool.query(query, params);

    res.json({ listings: rows });
  } catch (error) {
    console.error("Browse marketplace error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Get listing details
marketplace.get("/listings/:id", async (req, res) => {
  try {
    const { rows: listings } = await pool.query(
      `select l.*, p.name as publisher_name, p.id as publisher_id
       from marketplace_listings l
       join publishers p on p.id = l.publisher_id
       where l.id = $1 and l.visibility = 'public' and l.status = 'active'`,
      [req.params.id]
    );

    if (!listings.length) {
      return res.status(404).json({ error: "listing not found" });
    }

    const listing = listings[0];

    // Get versions
    const { rows: versions } = await pool.query(
      `select version, engine_min, engine_max, size_bytes, changelog, is_prerelease, created_at
       from marketplace_versions
       where listing_id = $1
       order by created_at desc`,
      [req.params.id]
    );

    // Get recent reviews
    const { rows: reviews } = await pool.query(
      `select r.rating, r.title, r.comment, r.version, r.created_at, u.username
       from marketplace_reviews r
       join users u on u.id = r.user_id
       where r.listing_id = $1
       order by r.created_at desc
       limit 10`,
      [req.params.id]
    );

    res.json({
      listing,
      versions,
      reviews
    });
  } catch (error) {
    console.error("Get listing error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Get marketplace categories
marketplace.get("/categories", async (req, res) => {
  try {
    const { rows } = await pool.query(
      "select name, description, icon from marketplace_categories where active = true order by sort_order"
    );
    res.json({ categories: rows });
  } catch (error) {
    console.error("Get categories error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Download package (requires authentication and entitlement check)
marketplace.get("/packages/:listing_id/:version", authRequired, async (req, res) => {
  try {
    const { listing_id, version } = req.params;

    // Check if user has entitlement to this package
    const { rows: entitlements } = await pool.query(
      `select e.id from marketplace_entitlements e
       where e.user_id = $1 and e.listing_id = $2 and e.status = 'active'
       and (e.expires_at is null or e.expires_at > now())`,
      [req.user.user_id, listing_id]
    );

    if (!entitlements.length) {
      return res.status(403).json({ error: "no valid entitlement for this package" });
    }

    // Get package version info
    const { rows: versions } = await pool.query(
      `select storage_url, sha256, manifest, signature
       from marketplace_versions
       where listing_id = $1 and version = $2`,
      [listing_id, version]
    );

    if (!versions.length) {
      return res.status(404).json({ error: "version not found" });
    }

    const versionInfo = versions[0];

    // Record download analytics
    await pool.query(
      `insert into marketplace_analytics(listing_id, user_id, event_type, version, metadata)
       values($1, $2, 'download', $3, '{}')`,
      [listing_id, req.user.user_id, version]
    );

    res.json({
      download_url: versionInfo.storage_url,
      sha256: versionInfo.sha256,
      manifest: versionInfo.manifest,
      signature: versionInfo.signature
    });
  } catch (error) {
    console.error("Download package error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// User's purchased/installed packages
marketplace.get("/my-packages", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      `select
         l.id, l.key, l.title, l.latest_version,
         e.version as entitled_version, e.seats, e.expires_at,
         i.version as installed_version, i.status as install_status,
         p.name as publisher_name
       from marketplace_entitlements e
       join marketplace_listings l on l.id = e.listing_id
       join publishers p on p.id = l.publisher_id
       left join marketplace_installs i on i.listing_id = l.id and i.user_id = e.user_id
       where e.user_id = $1 and e.status = 'active'
       order by e.created_at desc`,
      [req.user.user_id]
    );

    res.json({ packages: rows });
  } catch (error) {
    console.error("Get my packages error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Submit review
marketplace.post("/listings/:id/reviews", authRequired, async (req, res) => {
  try {
    const { rating, title, comment, version } = req.body || {};
    const listing_id = req.params.id;

    if (!rating || rating < 1 || rating > 5) {
      return res.status(400).json({ error: "rating must be between 1 and 5" });
    }

    // Check if user has entitlement to review this package
    const { rows: entitlements } = await pool.query(
      `select id from marketplace_entitlements
       where user_id = $1 and listing_id = $2 and status = 'active'`,
      [req.user.user_id, listing_id]
    );

    if (!entitlements.length) {
      return res.status(403).json({ error: "can only review packages you own" });
    }

    const { rows } = await pool.query(
      `insert into marketplace_reviews(user_id, listing_id, rating, title, comment, version)
       values($1, $2, $3, $4, $5, $6)
       on conflict(user_id, listing_id)
       do update set rating = excluded.rating, title = excluded.title, comment = excluded.comment, version = excluded.version, updated_at = now()
       returning id, rating, created_at`,
      [req.user.user_id, listing_id, rating, title || null, comment || null, version || null]
    );

    res.json({ review: rows[0] });
  } catch (error) {
    console.error("Submit review error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Purchase workflow package
marketplace.post("/purchase", authRequired, async (req, res) => {
  try {
    const { listing_id, quantity = 1, version = null } = req.body || {};

    if (!listing_id) {
      return res.status(400).json({ error: "listing_id required" });
    }

    // Get listing details
    const { rows: listings } = await pool.query(
      `select l.*, p.name as publisher_name
       from marketplace_listings l
       join publishers p on p.id = l.publisher_id
       where l.id = $1 and l.visibility = 'public' and l.status = 'active'`,
      [listing_id]
    );

    if (!listings.length) {
      return res.status(404).json({ error: "listing not found" });
    }

    const listing = listings[0];
    const totalAmount = listing.price_cents * quantity;

    // Create order
    const { rows: orders } = await pool.query(
      `insert into marketplace_orders(user_id, listing_id, version, quantity, amount_cents, currency, provider, status)
       values($1, $2, $3, $4, $5, $6, 'stripe', 'pending') returning *`,
      [req.user.user_id, listing_id, version, quantity, totalAmount, listing.currency]
    );

    const order = orders[0];

    // For free packages, auto-approve
    if (totalAmount === 0) {
      await processOrderPayment(order.id, 'free_package');
      const { rows: updatedOrders } = await pool.query(
        "select * from marketplace_orders where id = $1",
        [order.id]
      );
      return res.json({ order: updatedOrders[0], status: 'completed' });
    }

    // For paid packages, integrate with billing system
    const { createCheckoutSession } = await import('./payments/stripe.js');

    // Get user info for checkout
    const { rows: users } = await pool.query(
      "select id, email, stripe_customer_id from users where id = $1",
      [req.user.user_id]
    );

    if (!users.length) {
      return res.status(404).json({ error: "user not found" });
    }

    const user = users[0];

    // Create checkout session for the purchase
    const checkoutSession = await createCheckoutSession({
      user,
      plan: `marketplace_${listing_id}`,
      mode: 'payment',
      success_url: `${process.env.APP_URL || 'http://localhost:3000'}/marketplace/purchase/success?order_id=${order.id}`,
      cancel_url: `${process.env.APP_URL || 'http://localhost:3000'}/marketplace/purchase/cancel?order_id=${order.id}`
    });

    // Update order with external ID
    await pool.query(
      "update marketplace_orders set external_order_id = $1 where id = $2",
      [checkoutSession.id, order.id]
    );

    res.json({
      order,
      checkout_url: checkoutSession.url,
      status: 'pending_payment'
    });
  } catch (error) {
    console.error("Purchase error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Process order payment (called by webhooks)
async function processOrderPayment(orderId, paymentId) {
  try {
    // Get order details
    const { rows: orders } = await pool.query(
      "select * from marketplace_orders where id = $1",
      [orderId]
    );

    if (!orders.length) {
      throw new Error(`Order ${orderId} not found`);
    }

    const order = orders[0];

    // Update order status
    await pool.query(
      "update marketplace_orders set status = 'paid', paid_at = now() where id = $1",
      [orderId]
    );

    // Create entitlement
    const expiresAt = null; // Permanent license for one-time purchases
    const { rows: entitlements } = await pool.query(
      `insert into marketplace_entitlements(user_id, listing_id, version, seats, device_bound, status, expires_at, created_via_order)
       values($1, $2, $3, $4, true, 'active', $5, $6) returning *`,
      [order.user_id, order.listing_id, order.version, order.quantity, expiresAt, orderId]
    );

    console.log(`Created entitlement ${entitlements[0].id} for order ${orderId}`);

    // Record purchase analytics
    await pool.query(
      `insert into marketplace_analytics(listing_id, user_id, event_type, metadata)
       values($1, $2, 'purchase', $3)`,
      [order.listing_id, order.user_id, JSON.stringify({ order_id: orderId, amount_cents: order.amount_cents })]
    );

    return entitlements[0];
  } catch (error) {
    console.error(`Error processing order payment ${orderId}:`, error);
    throw error;
  }
}

// Check user's entitlement to a specific package
marketplace.get("/entitlements/:listing_id", authRequired, async (req, res) => {
  try {
    const { rows } = await pool.query(
      `select e.*, l.title, l.latest_version
       from marketplace_entitlements e
       join marketplace_listings l on l.id = e.listing_id
       where e.user_id = $1 and e.listing_id = $2 and e.status = 'active'
       and (e.expires_at is null or e.expires_at > now())`,
      [req.user.user_id, req.params.listing_id]
    );

    if (!rows.length) {
      return res.status(404).json({ error: "no active entitlement found" });
    }

    res.json({ entitlement: rows[0] });
  } catch (error) {
    console.error("Check entitlement error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Install package on device
marketplace.post("/install", authRequired, async (req, res) => {
  try {
    const { listing_id, device_id, version } = req.body || {};

    if (!listing_id || !device_id) {
      return res.status(400).json({ error: "listing_id and device_id required" });
    }

    // Check entitlement
    const { rows: entitlements } = await pool.query(
      `select * from marketplace_entitlements
       where user_id = $1 and listing_id = $2 and status = 'active'
       and (expires_at is null or expires_at > now())`,
      [req.user.user_id, listing_id]
    );

    if (!entitlements.length) {
      return res.status(403).json({ error: "no valid entitlement for this package" });
    }

    const entitlement = entitlements[0];

    // Check device ownership
    const { rows: devices } = await pool.query(
      "select id from devices where id = $1 and user_id = $2",
      [device_id, req.user.user_id]
    );

    if (!devices.length) {
      return res.status(403).json({ error: "device not found or not owned by user" });
    }

    // Check seat limits
    const { rows: currentInstalls } = await pool.query(
      "select count(*) as install_count from marketplace_installs where listing_id = $1 and user_id = $2 and status = 'installed'",
      [listing_id, req.user.user_id]
    );

    if (parseInt(currentInstalls[0].install_count) >= entitlement.seats) {
      return res.status(403).json({ error: "seat limit exceeded" });
    }

    // Get latest version if not specified
    let installVersion = version;
    if (!installVersion) {
      const { rows: listings } = await pool.query(
        "select latest_version from marketplace_listings where id = $1",
        [listing_id]
      );
      installVersion = listings[0]?.latest_version;
    }

    if (!installVersion) {
      return res.status(400).json({ error: "no version available for installation" });
    }

    // Create or update installation
    const { rows } = await pool.query(
      `insert into marketplace_installs(user_id, device_id, listing_id, version, status, auto_update, last_used_at)
       values($1, $2, $3, $4, 'installed', true, now())
       on conflict(device_id, listing_id)
       do update set version = excluded.version, status = excluded.status, updated_at = now()
       returning *`,
      [req.user.user_id, device_id, listing_id, installVersion]
    );

    // Record installation analytics
    await pool.query(
      `insert into marketplace_analytics(listing_id, user_id, device_id, event_type, version)
       values($1, $2, $3, 'install', $4)`,
      [listing_id, req.user.user_id, device_id, installVersion]
    );

    res.json({ installation: rows[0] });
  } catch (error) {
    console.error("Install package error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Uninstall package from device
marketplace.delete("/install/:device_id/:listing_id", authRequired, async (req, res) => {
  try {
    const { device_id, listing_id } = req.params;

    // Check device ownership
    const { rows: devices } = await pool.query(
      "select id from devices where id = $1 and user_id = $2",
      [device_id, req.user.user_id]
    );

    if (!devices.length) {
      return res.status(403).json({ error: "device not found or not owned by user" });
    }

    // Update installation status
    const { rows } = await pool.query(
      `update marketplace_installs
       set status = 'uninstalled', updated_at = now()
       where device_id = $1 and listing_id = $2 and user_id = $3
       returning *`,
      [device_id, listing_id, req.user.user_id]
    );

    if (!rows.length) {
      return res.status(404).json({ error: "installation not found" });
    }

    // Record uninstall analytics
    await pool.query(
      `insert into marketplace_analytics(listing_id, user_id, device_id, event_type, version)
       values($1, $2, $3, 'uninstall', $4)`,
      [listing_id, req.user.user_id, device_id, rows[0].version]
    );

    res.json({ message: "package uninstalled successfully" });
  } catch (error) {
    console.error("Uninstall package error:", error);
    return res.status(500).json({ error: "internal error" });
  }
});

// Export the payment processing function for use by webhooks
export { processOrderPayment };