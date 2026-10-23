#!/usr/bin/env python3
"""
Sprint J: €ıSåw
šID‡öS: .wfpack.tgz </~ŒÁ
"""

import argparse
import hashlib
import json
import tarfile
import tempfile
import yaml
import logging
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# û yî9îU0ï„
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SkillPackager:
    """€ıSh"""

    def __init__(self, signature_key: str = None):
        """
        ËSh

        Args:
            signature_key: ~Æ¥‚œĞ›(Ø¤<
        """
        self.signature_key = signature_key or "sprint_j_skill_signature_key"

    def pack_skill(self, skill_yaml_path: str, output_path: str = None,
                   include_resources: List[str] = None, metadata: Dict[str, Any] = None) -> str:
        """
        S€ı: .wfpack.tgz ‡ö

        Args:
            skill_yaml_path: €ıYAMLšI‡öï„
            output_path: “ú‡öï„‚œšê¨
            include_resources: +„D‡öh
            metadata: „Cpn

        Returns:
            „‡öï„
        """
        skill_path = Path(skill_yaml_path)
        if not skill_path.exists():
            raise FileNotFoundError(f"€ıšI‡öX(: {skill_yaml_path}")

        # ûÖvŒÁ€ıšI
        with open(skill_path, 'r', encoding='utf-8') as f:
            skill_data = yaml.safe_load(f)

        self._validate_skill_definition(skill_data)

        # “ú‡öï„
        if not output_path:
            skill_name = skill_data['name']
            version = skill_data['version']
            output_path = f"{skill_name}-{version}.wfpack.tgz"

        output_path = Path(output_path)

        # ~
        signature = self._generate_signature(skill_data)

        # úmanifest
        manifest = self._create_manifest(skill_data, signature, include_resources, metadata)

        # ú‡ö
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # 6€ıšI‡ö
            skill_file_name = "skill.yaml"
            skill_temp_path = temp_path / skill_file_name
            with open(skill_temp_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(skill_data, f, sort_keys=False, allow_unicode=True)

            # úmanifest‡ö
            manifest_path = temp_path / "manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            # 6D‡ö
            if include_resources:
                resources_dir = temp_path / "resources"
                resources_dir.mkdir()

                for resource_path in include_resources:
                    if Path(resource_path).exists():
                        import shutil
                        shutil.copy2(resource_path, resources_dir)
                        logger.info(f"+D‡ö: {resource_path}")

            # útar.gz‡ö
            with tarfile.open(output_path, 'w:gz') as tar:
                for file_path in temp_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(temp_path)
                        tar.add(file_path, arcname=arcname)

        logger.info(f"€ıúŸ: {output_path}")
        return str(output_path)

    def unpack_skill(self, package_path: str, output_dir: str = None, verify_signature: bool = True) -> Dict[str, Any]:
        """
        ã€ı‡ö

        Args:
            package_path: ‡öï„
            output_dir: ã“úîU
            verify_signature: /&ŒÁ~

        Returns:
            ãÓœáo
        """
        package_path = Path(package_path)
        if not package_path.exists():
            raise FileNotFoundError(f"‡öX(: {package_path}")

        if not output_dir:
            output_dir = package_path.stem

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            # ã‹‡ö
            with tarfile.open(package_path, 'r:gz') as tar:
                tar.extractall(output_path)

            # ûÖmanifest
            manifest_path = output_path / "manifest.json"
            if not manifest_path.exists():
                raise ValueError("‡ö-:manifest.json")

            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            # ûÖ€ıšI
            skill_file = manifest.get('skill_file', 'skill.yaml')
            skill_path = output_path / skill_file

            if not skill_path.exists():
                raise ValueError(f"‡ö-:€ıšI‡ö: {skill_file}")

            with open(skill_path, 'r', encoding='utf-8') as f:
                skill_data = yaml.safe_load(f)

            # ŒÁ~
            if verify_signature:
                expected_signature = manifest.get('signature')
                if not expected_signature:
                    raise ValueError("‡ö-:~áo")

                actual_signature = self._generate_signature(skill_data)
                if actual_signature != expected_signature:
                    raise ValueError("‡ö~ŒÁ1%")

                logger.info("~ŒÁŸ")

            # ŒÁ€ıšI
            self._validate_skill_definition(skill_data)

            result = {
                "skill_data": skill_data,
                "manifest": manifest,
                "output_dir": str(output_path),
                "verified": verify_signature
            }

            logger.info(f"€ıãŸ: {package_path}")
            return result

        except Exception as e:
            logger.error(f"ã1%: {e}")
            raise

    def verify_package(self, package_path: str) -> Dict[str, Any]:
        """
        ŒÁ€ı„Œt'Œ‰h'

        Args:
            package_path: ‡öï„

        Returns:
            ŒÁÓœ
        """
        try:
            # 4öãÛLŒÁ
            with tempfile.TemporaryDirectory() as temp_dir:
                result = self.unpack_skill(package_path, temp_dir, verify_signature=True)

                skill_data = result["skill_data"]
                manifest = result["manifest"]

                # ‰h'Àå
                security_issues = self._check_security(skill_data)

                # Œt'Àå
                integrity_issues = self._check_integrity(skill_data, manifest)

                verification_result = {
                    "valid": len(security_issues) == 0 and len(integrity_issues) == 0,
                    "skill_name": skill_data.get("name"),
                    "version": skill_data.get("version"),
                    "signature_verified": result["verified"],
                    "security_issues": security_issues,
                    "integrity_issues": integrity_issues,
                    "package_size": Path(package_path).stat().st_size,
                    "verified_at": datetime.now().isoformat()
                }

                return verification_result

        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "verified_at": datetime.now().isoformat()
            }

    def _validate_skill_definition(self, skill_data: Dict[str, Any]):
        """ŒÁ€ıšI„	H'"""
        required_fields = ['name', 'version', 'title', 'description', 'host', 'microplan']

        for field in required_fields:
            if field not in skill_data:
                raise ValueError(f"€ıšI:ÅWµ: {field}")

        # ŒÁH,<
        version = skill_data['version']
        if not self._is_valid_version(version):
            raise ValueError(f"H,÷<cn: {version}")

        # ŒÁ®¡
        microplan = skill_data['microplan']
        if not self._validate_microplan(microplan):
            raise ValueError("®¡+‰h„¨\")

    def _is_valid_version(self, version: str) -> bool:
        """ŒÁH,÷<"""
        import re
        pattern = r'^\d+\.\d+\.\d+$'
        return bool(re.match(pattern, version))

    def _validate_microplan(self, microplan: Dict[str, Any]) -> bool:
        """ŒÁ®¡„‰h'"""
        if "steps" not in microplan:
            return False

        allowed_actions = {
            "click_coordinates", "wheel_coordinates", "wait_for",
            "ext.extract", "ext.get_pagestate", "sleep_ms", "type_text"
        }

        for step in microplan["steps"]:
            if "do" not in step:
                return False

            action = step["do"]
            if action not in allowed_actions:
                return False

            # ÀåÂp‰h'
            args = step.get("args", {})
            if not self._validate_step_args(args):
                return False

        return True

    def _validate_step_args(self, args: Dict[str, Any]) -> bool:
        """ŒÁe¤Âp„‰h'"""
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("@"):
                # ÀåØÏ(/&‰h
                var_ref = value[1:]
                if not self._is_safe_variable_reference(var_ref):
                    return False

        return True

    def _is_safe_variable_reference(self, var_ref: str) -> bool:
        """ÀåØÏ(/&‰h"""
        safe_patterns = [
            "ps.", "i", "index_offset", "apply_texts", "last_found_bbox",
            "args.", "params.", "scroll_amount", "button_texts"
        ]

        return any(var_ref.startswith(pattern) or var_ref == pattern.rstrip('.') for pattern in safe_patterns)

    def _generate_signature(self, skill_data: Dict[str, Any]) -> str:
        """€ı~"""
        # Ä€ıpn
        normalized = json.dumps(skill_data, sort_keys=True, separators=(',', ':'))

        # ~
        signature_input = f"{normalized}:{self.signature_key}"
        return hashlib.sha256(signature_input.encode()).hexdigest()

    def _create_manifest(self, skill_data: Dict[str, Any], signature: str,
                        include_resources: List[str] = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """úmanifest‡ö"""
        manifest = {
            "format_version": "1.0",
            "skill_file": "skill.yaml",
            "signature": signature,
            "created_at": datetime.now().isoformat(),
            "skill_info": {
                "name": skill_data["name"],
                "version": skill_data["version"],
                "title": skill_data["title"],
                "host": skill_data["host"]
            }
        }

        if include_resources:
            manifest["resources"] = [Path(res).name for res in include_resources]

        if metadata:
            manifest["metadata"] = metadata

        return manifest

    def _check_security(self, skill_data: Dict[str, Any]) -> List[str]:
        """Àå‰h'î˜"""
        issues = []

        # Àå®¡‰h'
        microplan = skill_data.get("microplan", {})
        steps = microplan.get("steps", [])

        for i, step in enumerate(steps):
            action = step.get("do", "")

            # Àåqi¨\
            dangerous_actions = ["exec", "eval", "system", "subprocess"]
            if any(dangerous in action.lower() for dangerous in dangerous_actions):
                issues.append(f"e¤ {i+1} +qi¨\: {action}")

            # Àå‰h„Âp
            args = step.get("args", {})
            for key, value in args.items():
                if isinstance(value, str):
                    # Àå,èe
                    if any(pattern in value.lower() for pattern in ["<script", "javascript:", "eval("]):
                        issues.append(f"e¤ {i+1} Âp {key} ïı+,èe")

                    # Àåï„M†
                    if "../" in value or "..\\" in value:
                        issues.append(f"e¤ {i+1} Âp {key} ïı+ï„M†;û")

        return issues

    def _check_integrity(self, skill_data: Dict[str, Any], manifest: Dict[str, Any]) -> List[str]:
        """ÀåŒt'î˜"""
        issues = []

        # Àå€ıáo ô'
        manifest_info = manifest.get("skill_info", {})

        for field in ["name", "version", "title", "host"]:
            if skill_data.get(field) != manifest_info.get(field):
                issues.append(f"€ı {field} manifest ô")

        # Àå®¡Ó„
        microplan = skill_data.get("microplan", {})
        if "steps" not in microplan:
            issues.append("®¡:stepsWµ")
        elif len(microplan["steps"]) == 0:
            issues.append("®¡¡	šIûUe¤")

        # Àå¦_'
        constraints = skill_data.get("constraints", {})
        max_steps = constraints.get("max_steps")
        actual_steps = len(microplan.get("steps", []))

        if max_steps and actual_steps > max_steps:
            issues.append(f"Ee¤p ({actual_steps}) …Ç¦_P6 ({max_steps})")

        return issues

def main():
    """;ıp"""
    parser = argparse.ArgumentParser(description="€ıSåw")
    subparsers = parser.add_subparsers(dest="command", help="ï(}ä")

    # pack}ä
    pack_parser = subparsers.add_parser("pack", help="S€ı")
    pack_parser.add_argument("skill_yaml", help="€ıYAMLšI‡ö")
    pack_parser.add_argument("-o", "--output", help="“ú‡öï„")
    pack_parser.add_argument("-r", "--resources", nargs="*", help="+„D‡ö")
    pack_parser.add_argument("--metadata", help="CpnJSON<	")

    # unpack}ä
    unpack_parser = subparsers.add_parser("unpack", help="ã€ı")
    unpack_parser.add_argument("package", help="€ı‡ö")
    unpack_parser.add_argument("-o", "--output", help="“úîU")
    unpack_parser.add_argument("--no-verify", action="store_true", help="óÇ~ŒÁ")

    # verify}ä
    verify_parser = subparsers.add_parser("verify", help="ŒÁ€ı")
    verify_parser.add_argument("package", help="€ı‡ö")

    # ~Æ¥	y
    parser.add_argument("--signature-key", help="~Æ¥")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # úSh
    packager = SkillPackager(signature_key=args.signature_key)

    try:
        if args.command == "pack":
            # ãCpn
            metadata = None
            if args.metadata:
                metadata = json.loads(args.metadata)

            # S
            output_file = packager.pack_skill(
                skill_yaml_path=args.skill_yaml,
                output_path=args.output,
                include_resources=args.resources or [],
                metadata=metadata
            )

            print(f" €ıúŸ: {output_file}")

        elif args.command == "unpack":
            # ã
            result = packager.unpack_skill(
                package_path=args.package,
                output_dir=args.output,
                verify_signature=not args.no_verify
            )

            print(f" €ıãŸ: {result['output_dir']}")
            print(f"€ığ: {result['skill_data']['name']}")
            print(f"H,: {result['skill_data']['version']}")
            print(f"~ŒÁ: {'' if result['verified'] else 'L'}")

        elif args.command == "verify":
            # ŒÁ
            result = packager.verify_package(args.package)

            print(f"ŒÁÓœ: {' Ç' if result['valid'] else 'L 1%'}")

            if result.get("skill_name"):
                print(f"€ığ: {result['skill_name']}")
                print(f"H,: {result['version']}")

            print(f"~ŒÁ: {'' if result.get('signature_verified') else 'L'}")

            if result.get("security_issues"):
                print("\n= ‰hî˜:")
                for issue in result["security_issues"]:
                    print(f"  - {issue}")

            if result.get("integrity_issues"):
                print("\n= Œt'î˜:")
                for issue in result["integrity_issues"]:
                    print(f"  - {issue}")

            if result.get("error"):
                print(f"\nL ï: {result['error']}")

    except Exception as e:
        logger.error(f"Í\1%: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()