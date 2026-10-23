#!/usr/bin/env python3
"""
Client-side Marketplace Package Installation System

This module handles:
1. Package discovery and browsing
2. Purchase verification and entitlement checking
3. Secure package download and signature verification
4. Local installation and dependency management
5. Auto-update functionality
"""

import requests
import hashlib
import base64
import json
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, Optional, List
import nacl.signing
import semver

class MarketplaceClient:
    def __init__(self, api_base: str, token: str, device_id: str):
        self.api_base = api_base.rstrip('/')
        self.token = token
        self.device_id = device_id
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        self.install_dir = Path.home() / '.autoagent' / 'packages'
        self.install_dir.mkdir(parents=True, exist_ok=True)

    def browse_marketplace(self, category: str = None, search: str = None, featured: bool = None) -> Dict:
        """Browse available packages in the marketplace"""
        params = {}
        if category:
            params['category'] = category
        if search:
            params['search'] = search
        if featured:
            params['featured'] = 'true'

        response = requests.get(
            f"{self.api_base}/marketplace/browse",
            params=params,
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_package_details(self, listing_id: str) -> Dict:
        """Get detailed information about a specific package"""
        response = requests.get(
            f"{self.api_base}/marketplace/listings/{listing_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def check_entitlement(self, listing_id: str) -> Optional[Dict]:
        """Check if user has entitlement to a package"""
        try:
            response = requests.get(
                f"{self.api_base}/marketplace/entitlements/{listing_id}",
                headers=self.headers
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()['entitlement']
        except requests.RequestException:
            return None

    def purchase_package(self, listing_id: str, quantity: int = 1) -> Dict:
        """Purchase a package from the marketplace"""
        response = requests.post(
            f"{self.api_base}/marketplace/purchase",
            json={
                'listing_id': listing_id,
                'quantity': quantity
            },
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def download_package(self, listing_id: str, version: str = None) -> Dict:
        """Download a package with entitlement verification"""
        url = f"{self.api_base}/marketplace/packages/{listing_id}"
        if version:
            url += f"/{version}"
        else:
            # Get latest version
            details = self.get_package_details(listing_id)
            version = details['listing']['latest_version']
            url += f"/{version}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def verify_package_signature(self, package_bytes: bytes, signature: str, manifest: Dict) -> bool:
        """Verify package signature using ed25519"""
        try:
            # Calculate SHA256 hash
            package_hash = hashlib.sha256(package_bytes).digest()

            # Get publisher's public key from manifest
            publisher_pubkey = manifest['publisher']['pubkey_ed25519']

            # Decode signature and public key
            sig = base64.b64decode(signature)
            pubkey = base64.b64decode(publisher_pubkey)

            # Verify signature
            verify_key = nacl.signing.VerifyKey(pubkey)
            verify_key.verify(package_hash, sig)

            print(f"✅ Package signature verified for {manifest['name']}")
            return True
        except Exception as e:
            print(f"❌ Package signature verification failed: {e}")
            return False

    def validate_manifest(self, manifest: Dict) -> bool:
        """Validate package manifest requirements"""
        try:
            # Check required fields
            required_fields = ['key', 'name', 'version', 'publisher', 'engine', 'workflows']
            for field in required_fields:
                if field not in manifest:
                    print(f"❌ Missing required field: {field}")
                    return False

            # Check engine compatibility
            engine_min = manifest['engine']['min']
            current_engine = "0.4.0"  # Current engine version

            if not self._check_version_compatibility(current_engine, engine_min):
                print(f"❌ Engine version incompatible. Required: {engine_min}, Current: {current_engine}")
                return False

            # Validate workflows
            if not manifest.get('workflows'):
                print("❌ No workflows defined")
                return False

            entry_workflows = [w for w in manifest['workflows'] if w.get('entry')]
            if not entry_workflows:
                print("❌ No entry workflow defined")
                return False

            print(f"✅ Manifest validation passed for {manifest['name']}")
            return True
        except Exception as e:
            print(f"❌ Manifest validation failed: {e}")
            return False

    def _check_version_compatibility(self, current: str, required: str) -> bool:
        """Check if current version meets minimum requirement"""
        try:
            return semver.compare(current, required) >= 0
        except Exception:
            # Fallback to simple string comparison
            return current >= required

    def install_package(self, listing_id: str, version: str = None, force: bool = False) -> bool:
        """Install a package locally with signature verification"""
        try:
            print(f"📦 Installing package {listing_id}...")

            # Check entitlement first
            entitlement = self.check_entitlement(listing_id)
            if not entitlement:
                print("❌ No valid entitlement found. Please purchase this package first.")
                return False

            # Download package metadata
            download_info = self.download_package(listing_id, version)

            # Parse manifest
            manifest = json.loads(download_info['manifest']) if isinstance(download_info['manifest'], str) else download_info['manifest']

            # Validate manifest
            if not self.validate_manifest(manifest):
                return False

            # Create temporary file for download
            with tempfile.NamedTemporaryFile(suffix='.wfpack.tgz', delete=False) as tmp_file:
                # In a real implementation, this would download from the storage_url
                # For demo purposes, create a mock package
                mock_package = self._create_mock_package(manifest)
                tmp_file.write(mock_package)
                tmp_file.flush()

                # Verify file hash
                with open(tmp_file.name, 'rb') as f:
                    package_bytes = f.read()

                calculated_hash = hashlib.sha256(package_bytes).hexdigest()
                if calculated_hash != download_info['sha256']:
                    print(f"❌ Package hash verification failed")
                    os.unlink(tmp_file.name)
                    return False

                # Verify signature
                if not self.verify_package_signature(package_bytes, download_info['signature'], manifest):
                    os.unlink(tmp_file.name)
                    return False

                # Extract package to installation directory
                package_dir = self.install_dir / manifest['key']
                if package_dir.exists() and not force:
                    print(f"❌ Package already installed at {package_dir}. Use force=True to overwrite.")
                    os.unlink(tmp_file.name)
                    return False

                # Create package directory
                package_dir.mkdir(parents=True, exist_ok=True)

                # Extract package
                with tarfile.open(tmp_file.name, 'r:gz') as tar:
                    tar.extractall(package_dir)

                # Clean up
                os.unlink(tmp_file.name)

            # Record installation
            install_response = requests.post(
                f"{self.api_base}/marketplace/install",
                json={
                    'listing_id': listing_id,
                    'device_id': self.device_id,
                    'version': manifest['version']
                },
                headers=self.headers
            )
            install_response.raise_for_status()

            # Save installation metadata
            install_meta = {
                'listing_id': listing_id,
                'version': manifest['version'],
                'installed_at': install_response.json()['installation']['created_at'],
                'manifest': manifest
            }

            with open(package_dir / '.install_meta.json', 'w') as f:
                json.dump(install_meta, f, indent=2)

            print(f"✅ Package {manifest['name']} v{manifest['version']} installed successfully")
            print(f"📂 Installation location: {package_dir}")
            return True

        except Exception as e:
            print(f"❌ Installation failed: {e}")
            return False

    def _create_mock_package(self, manifest: Dict) -> bytes:
        """Create a mock package for demonstration"""
        # Create a simple tar.gz with manifest and sample workflow
        with tempfile.NamedTemporaryFile(suffix='.tar.gz') as tmp:
            with tarfile.open(tmp.name, 'w:gz') as tar:
                # Add manifest
                manifest_data = json.dumps(manifest, indent=2).encode('utf-8')
                info = tarfile.TarInfo('manifest.json')
                info.size = len(manifest_data)
                tar.addfile(info, fileobj=tempfile.BytesIO(manifest_data))

                # Add sample workflow
                workflow = {
                    "start": "demo",
                    "states": {
                        "demo": {
                            "actions": [{"do": "log", "message": f"Running {manifest['name']}"}]
                        }
                    }
                }
                workflow_data = json.dumps(workflow, indent=2).encode('utf-8')
                info = tarfile.TarInfo('workflows/main.json')
                info.size = len(workflow_data)
                tar.addfile(info, fileobj=tempfile.BytesIO(workflow_data))

            # Return the package bytes
            with open(tmp.name, 'rb') as f:
                return f.read()

    def list_installed_packages(self) -> List[Dict]:
        """List locally installed packages"""
        installed = []
        for package_dir in self.install_dir.iterdir():
            if package_dir.is_dir():
                meta_file = package_dir / '.install_meta.json'
                if meta_file.exists():
                    try:
                        with open(meta_file) as f:
                            meta = json.load(f)
                        installed.append({
                            'key': meta['manifest']['key'],
                            'name': meta['manifest']['name'],
                            'version': meta['version'],
                            'installed_at': meta['installed_at'],
                            'path': str(package_dir)
                        })
                    except Exception as e:
                        print(f"❌ Error reading metadata for {package_dir}: {e}")
        return installed

    def uninstall_package(self, listing_id: str) -> bool:
        """Uninstall a package"""
        try:
            # Find package by listing_id
            installed = self.list_installed_packages()
            package_info = None

            for pkg in installed:
                if pkg.get('listing_id') == listing_id:
                    package_info = pkg
                    break

            if not package_info:
                print(f"❌ Package {listing_id} not found")
                return False

            # Remove from server
            response = requests.delete(
                f"{self.api_base}/marketplace/install/{self.device_id}/{listing_id}",
                headers=self.headers
            )
            response.raise_for_status()

            # Remove local files
            package_path = Path(package_info['path'])
            if package_path.exists():
                import shutil
                shutil.rmtree(package_path)

            print(f"✅ Package {package_info['name']} uninstalled successfully")
            return True

        except Exception as e:
            print(f"❌ Uninstall failed: {e}")
            return False

    def check_for_updates(self) -> List[Dict]:
        """Check for available updates to installed packages"""
        updates_available = []
        installed = self.list_installed_packages()

        for package in installed:
            try:
                # Get latest version from marketplace
                details = self.get_package_details(package.get('listing_id', ''))
                latest_version = details['listing']['latest_version']
                current_version = package['version']

                if semver.compare(latest_version, current_version) > 0:
                    updates_available.append({
                        'package': package,
                        'current_version': current_version,
                        'latest_version': latest_version
                    })
            except Exception as e:
                print(f"❌ Error checking updates for {package['name']}: {e}")

        return updates_available

def main():
    """Demo CLI for marketplace client"""
    import argparse

    parser = argparse.ArgumentParser(description='AutoAgent Marketplace Client')
    parser.add_argument('--api-base', default='http://localhost:8080', help='API base URL')
    parser.add_argument('--token', required=True, help='Authentication token')
    parser.add_argument('--device-id', required=True, help='Device ID')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Browse command
    browse_parser = subparsers.add_parser('browse', help='Browse marketplace')
    browse_parser.add_argument('--category', help='Filter by category')
    browse_parser.add_argument('--search', help='Search term')
    browse_parser.add_argument('--featured', action='store_true', help='Show only featured packages')

    # Install command
    install_parser = subparsers.add_parser('install', help='Install package')
    install_parser.add_argument('listing_id', help='Package listing ID')
    install_parser.add_argument('--version', help='Specific version to install')
    install_parser.add_argument('--force', action='store_true', help='Force reinstall')

    # List command
    subparsers.add_parser('list', help='List installed packages')

    # Uninstall command
    uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall package')
    uninstall_parser.add_argument('listing_id', help='Package listing ID')

    # Updates command
    subparsers.add_parser('updates', help='Check for updates')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    client = MarketplaceClient(args.api_base, args.token, args.device_id)

    try:
        if args.command == 'browse':
            results = client.browse_marketplace(
                category=args.category,
                search=args.search,
                featured=args.featured
            )
            print("📱 Marketplace Packages:")
            for listing in results['listings']:
                print(f"  {listing['title']} (${listing['price_cents']/100:.2f})")
                print(f"    ID: {listing['id']}")
                print(f"    Category: {listing['category']}")
                print(f"    Publisher: {listing['publisher_name']}")
                print()

        elif args.command == 'install':
            success = client.install_package(args.listing_id, args.version, args.force)
            if not success:
                exit(1)

        elif args.command == 'list':
            packages = client.list_installed_packages()
            print("📦 Installed Packages:")
            for pkg in packages:
                print(f"  {pkg['name']} v{pkg['version']}")
                print(f"    Key: {pkg['key']}")
                print(f"    Installed: {pkg['installed_at']}")
                print()

        elif args.command == 'uninstall':
            success = client.uninstall_package(args.listing_id)
            if not success:
                exit(1)

        elif args.command == 'updates':
            updates = client.check_for_updates()
            if updates:
                print("🔄 Updates Available:")
                for update in updates:
                    pkg = update['package']
                    print(f"  {pkg['name']}: {update['current_version']} → {update['latest_version']}")
            else:
                print("✅ All packages are up to date")

    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)

if __name__ == '__main__':
    main()