#!/usr/bin/env python3
"""
Sprint J CLIåw
Ğ›€ı“¡¨\˜SÑŒÑ§„}äL¥ã
"""

import asyncio
import argparse
import json
import sys
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import logging
import aiohttp
from datetime import datetime

# û yî9îU0ï„
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.macros.registry import REGISTRY, get_registry_info
from tools.skill_packager import SkillPackager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SprintJCLI:
    """Sprint JŸı„CLIåw"""

    def __init__(self):
        self.api_endpoints = {
            "skills": "http://127.0.0.1:8006",
            "monitor": "http://127.0.0.1:8007"
        }
        self.packager = SkillPackager()

    # ===== €ı¡}ä =====

    async def list_skills_command(self, args):
        """ú€ı"""
        print("=Ë €ı“h")
        print("=" * 50)

        try:
            # ÎAPI·Ö€ıh
            params = {}
            if args.host:
                params["host"] = args.host
            if args.status:
                params["status"] = args.status

            skills_data = await self._call_api("GET", "skills", "/skills/list", params=params)

            if skills_data and skills_data.get("skills"):
                skills = skills_data["skills"]
                total = skills_data.get("total", len(skills))

                print(f"~0 {total} *€ı:")
                print()

                for skill in skills:
                    status_icon = self._get_status_icon(skill["status"])
                    print(f"{status_icon} {skill['name']} v{skill['version']}")
                    print(f"    ;:: {skill['host']}")
                    print(f"    ˜: {skill['title']}")
                    print(f"    ¶: {skill['status']}")
                    print(f"    e¤p: {len(skill.get('microplan', {}).get('steps', []))}")
                    print(f"    úöô: {skill['created_at']}")
                    print()

            else:
                print("¡	~0€ı")

        except Exception as e:
            print(f"L ·Ö€ıh1%: {e}")

    async def mine_skills_command(self, args):
        """˜€ı"""
        print("Ï ‘AP˜")
        print("=" * 50)

        cmd_args = [
            "python", "jobs/skills/mine_subsequences.py",
            f"--min-support={args.min_support}",
            f"--max-length={args.max_length}",
            f"--min-reward={args.min_reward}",
            f"--output-dir={args.output_dir}"
        ]

        if args.host:
            cmd_args.append(f"--host={args.host}")
        if args.goal:
            cmd_args.append(f"--goal={args.goal}")
        if args.start_date:
            cmd_args.append(f"--start-date={args.start_date}")
        if args.end_date:
            cmd_args.append(f"--end-date={args.end_date}")

        print(f"gL}ä: {' '.join(cmd_args)}")
        print()

        try:
            result = subprocess.run(cmd_args, capture_output=True, text=True, cwd=Path(__file__).parent.parent)

            if result.returncode == 0:
                print(" €ı˜Œ")
                if result.stdout:
                    print(result.stdout)

                # Àå“ú‡ö
                output_dir = Path(args.output_dir)
                if output_dir.exists():
                    yaml_files = list(output_dir.glob("auto_skill_*.yaml"))
                    if yaml_files:
                        print(f"\n=Ä „€ı‡ö ({len(yaml_files)} *):")
                        for file_path in yaml_files:
                            print(f"  - {file_path}")
                    else:
                        print("*€ı‡ö")

            else:
                print("L €ı˜1%")
                if result.stderr:
                    print(result.stderr)

        except Exception as e:
            print(f"L ˜ï: {e}")

    async def pack_skill_command(self, args):
        """S€ı"""
        print("=æ S€ı")
        print("=" * 50)

        try:
            # ãD‡öh
            resources = []
            if args.resources:
                resources = [r.strip() for r in args.resources.split(",")]

            # ãCpn
            metadata = {}
            if args.metadata:
                metadata = json.loads(args.metadata)

            # gLS
            output_file = self.packager.pack_skill(
                skill_yaml_path=args.skill_yaml,
                output_path=args.output,
                include_resources=resources,
                metadata=metadata
            )

            print(f" €ıúŸ: {output_file}")

            # >:áo
            file_size = Path(output_file).stat().st_size
            print(f"‡ö': {file_size / 1024:.1f} KB")

            # ŒÁ
            print("\n= ŒÁ€ı...")
            verification = self.packager.verify_package(output_file)

            if verification["valid"]:
                print(" ŒÁÇ")
            else:
                print("L ŒÁ1%")
                if verification.get("security_issues"):
                    print("‰hî˜:")
                    for issue in verification["security_issues"]:
                        print(f"  - {issue}")
                if verification.get("integrity_issues"):
                    print("Œt'î˜:")
                    for issue in verification["integrity_issues"]:
                        print(f"  - {issue}")

        except Exception as e:
            print(f"L S1%: {e}")

    async def publish_skill_command(self, args):
        """Ñ€ı"""
        print("=€ Ñ€ı")
        print("=" * 50)

        try:
            # ûÖ€ıšI
            with open(args.skill_yaml, 'r', encoding='utf-8') as f:
                import yaml
                skill_data = yaml.safe_load(f)

            # „úÑ÷B
            publish_data = {
                "name": skill_data["name"],
                "title": skill_data["title"],
                "description": skill_data["description"],
                "host": skill_data["host"],
                "version": skill_data["version"],
                "params": skill_data.get("params", {}),
                "constraints": skill_data.get("constraints", {}),
                "microplan": skill_data["microplan"]
            }

            print(f"Ñ€ı: {skill_data['name']} v{skill_data['version']}")
            print(f"î;:: {skill_data['host']}")
            print()

            # (ÑAPI
            result = await self._call_api("POST", "skills", "/skills/publish", json=publish_data)

            if result and result.get("success"):
                print(" €ıÑŸ")
                print(f"ˆo: {result.get('message', '')}")
            else:
                print("L €ıÑ1%")
                if result:
                    print(f"ï: {result.get('message', '*åï')}")

        except Exception as e:
            print(f"L Ñï: {e}")

    async def install_skill_command(self, args):
        """‰Å€ı"""
        print("=¾ ‰Å€ı")
        print("=" * 50)

        try:
            install_data = {
                "skill_name": args.name,
                "version": args.version,
                "host": args.host
            }

            print(f"‰Å€ı: {args.name} v{args.version}")
            if args.host:
                print(f"î;:: {args.host}")
            print()

            # (‰ÅAPI
            result = await self._call_api("POST", "skills", "/skills/install",
                                        json=install_data, params={"device_id": args.device_id})

            if result and result.get("success"):
                print(" €ı‰ÅŸ")
                print(f"ˆo: {result.get('message', '')}")
            else:
                print("L €ı‰Å1%")
                if result:
                    print(f"ï: {result.get('message', '*åï')}")

        except Exception as e:
            print(f"L ‰Åï: {e}")

    # ===== Ñ§}ä =====

    async def dashboard_command(self, args):
        """>:Ñ§êhØ"""
        print("=Ê €ıÑ§êhØ")
        print("=" * 50)

        try:
            params = {"days": args.days}
            if args.host:
                params["host"] = args.host

            dashboard_data = await self._call_api("GET", "monitor", "/skills/monitor/dashboard", params=params)

            if dashboard_data:
                summary = dashboard_data["summary"]
                print(f"=È ‚ß¡ ( Ñ {summary['period_days']} ))")
                print(f"  ;€ıp: {summary['total_skills']}")
                print(f"  ‰Êß: {summary['total_hosts']}")
                print(f"  ;gL!p: {summary['total_runs']}")
                print(f"  Ÿ!p: {summary['total_success']}")
                print(f"  tSŸ‡: {summary['overall_success_rate']:.1%}")
                print(f"  sGöß: {summary['avg_latency']}ms")
                print(f"  ;,: ${summary['total_cost']:.4f}")

                # íè€ı
                top_skills = dashboard_data["top_skills"][:5]
                if top_skills:
                    print(f"\n=% íè€ı (M5)")
                    for i, skill in enumerate(top_skills, 1):
                        print(f"  {i}. {skill['skill_name']} v{skill['version']}")
                        print(f"     ;:: {skill['host']}")
                        print(f"     gL!p: {skill['runs']}, Ÿ‡: {skill['success_rate']:.1%}")
                        print(f"     sGöß: {skill['avg_latency_ms']}ms")

                # ß
                host_dist = dashboard_data["host_distribution"]
                if host_dist:
                    print(f"\n< ß")
                    for host, runs in list(host_dist.items())[:5]:
                        print(f"  {host}: {runs} !")

            else:
                print("àÕ·ÖêhØpn")

        except Exception as e:
            print(f"L ·ÖêhØ1%: {e}")

    async def errors_command(self, args):
        """>:ï"""
        print("=¨ €ıï")
        print("=" * 50)

        try:
            params = {"days": args.days, "limit": args.limit}
            if args.skill:
                params["skill_name"] = args.skill

            errors_data = await self._call_api("GET", "monitor", "/skills/monitor/errors", params=params)

            if errors_data:
                print(f" Ñ {args.days} )„ï:")
                print()

                for error in errors_data:
                    print(f"L {error['skill_name']} v{error['version']}")
                    print(f"   ï{‹: {error['error_type']}")
                    print(f"   ï!p: {error['error_count']}")
                    print(f"   ï‡: {error['error_rate']:.1%}")
                    print(f"   :‹ï: {error['sample_error'][:100]}...")
                    print()

                if not errors_data:
                    print(" ¡	Ñ°ï")

            else:
                print("àÕ·Öïpn")

        except Exception as e:
            print(f"L ·Öï1%: {e}")

    async def real_time_command(self, args):
        """>:ö"""
        print("¡ ö€ıgL")
        print("=" * 50)

        try:
            real_time_data = await self._call_api("GET", "monitor", "/skills/monitor/real-time",
                                                params={"limit": args.limit})

            if real_time_data:
                stats = real_time_data["recent_stats"]
                print(f"=Ê  Ñ5Ÿß¡:")
                print(f"  ;gL!p: {stats['total_runs']}")
                print(f"  Ÿ!p: {stats['successful_runs']}")
                print(f"  Ÿ‡: {stats['success_rate']:.1%}")
                print(f"  sGöß: {stats['avg_latency']}ms")
                print(f"  ;Ã€ıp: {stats['active_skills']}")

                #  ÑgL
                executions = real_time_data["recent_executions"][:10]
                if executions:
                    print(f"\n=P  ÑgL (M10*):")
                    for exec_data in executions:
                        status_icon = "" if exec_data["success"] else "L"
                        print(f"  {status_icon} {exec_data['skill_name']} v{exec_data['version']}")
                        print(f"     ;:: {exec_data['host']}")
                        print(f"     ö: {exec_data['execution_time_ms']}ms")
                        print(f"      Ëöô: {exec_data['started_at']}")
                        if not exec_data["success"] and exec_data["error_message"]:
                            print(f"     ï: {exec_data['error_message'][:50]}...")

            else:
                print("àÕ·Ööpn")

        except Exception as e:
            print(f"L ·Öö1%: {e}")

    # ===== èŒh}ä =====

    async def registry_info_command(self, args):
        """>:èŒháo"""
        print("=Ú èŒháo")
        print("=" * 50)

        try:
            info = get_registry_info()
            print(f"èŒhï„: {info['base_path']}")
            print(f"òèŒpÏ: {info['total_macros']}")
            print(f";H,pÏ: {info['total_versions']}")
            print(f" }öô: {info['registry_loaded_at']}")

            if info['hosts']:
                print(f"\n< 	ß:")
                for host, count in info['hosts'].items():
                    print(f"  {host}: {count} *")

            # ú@	òèŒ„
            all_macros = REGISTRY.list_all()
            if all_macros:
                print(f"\n=Ë òèŒ„:")
                for macro in all_macros:
                    print(f"  =Ä {macro.name} v{macro.version}")
                    print(f"     ;:: {macro.host}")
                    print(f"     ˜: {macro.title}")
                    print(f"     e¤p: {len(macro.microplan.get('steps', []))}")
                    if macro.file_path:
                        print(f"     ‡ö: {macro.file_path}")
                    print()

        except Exception as e:
            print(f"L ·ÖèŒháo1%: {e}")

    async def test_macro_command(self, args):
        """KÕšI"""
        print(">ê KÕšI")
        print("=" * 50)

        try:
            # ·ÖšI
            macro = REGISTRY.get(args.name, args.version)
            if not macro:
                print(f"L X(: {args.name}")
                if args.version:
                    print(f"H,: {args.version}")
                return

            print(f"KÕ: {macro.name} v{macro.version}")
            print(f";:: {macro.host}")
            print(f"e¤p: {len(macro.microplan.get('steps', []))}")
            print()

            # ŒÁšI
            if REGISTRY.validate_macro(macro.to_dict()):
                print(" šI	H")
            else:
                print("L šIàH")

            # >:e¤æÅ
            steps = macro.microplan.get("steps", [])
            if steps and args.verbose:
                print(f"\n=İ gLe¤:")
                for i, step in enumerate(steps, 1):
                    print(f"  {i}. {step.get('do', 'unknown')}")
                    if step.get("args"):
                        print(f"     Âp: {step['args']}")

            # >:ÂpšI
            if macro.params and args.verbose:
                print(f"\n™ ÂpšI:")
                for param_name, param_def in macro.params.items():
                    print(f"  {param_name}: {param_def.get('type', 'unknown')}")
                    if param_def.get("default"):
                        print(f"    Ø¤<: {param_def['default']}")

            # >:¦_
            if macro.constraints and args.verbose:
                print(f"\n= ¦_:")
                for constraint, value in macro.constraints.items():
                    print(f"  {constraint}: {value}")

        except Exception as e:
            print(f"L KÕ1%: {e}")

    # ===== …©¹Õ =====

    async def _call_api(self, method: str, service: str, endpoint: str, **kwargs):
        """(API"""
        if service not in self.api_endpoints:
            raise ValueError(f"*å¡: {service}")

        url = f"{self.api_endpoints[service]}{endpoint}"

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"APIï {response.status}: {error_text}")
                    return None

    def _get_status_icon(self, status: str) -> str:
        """·Ö¶ş"""
        icons = {
            "prod": "=â",
            "staging": "=á",
            "deprecated": "=4",
            "rollback": "ª"
        }
        return icons.get(status, "S")

def main():
    """;ıp"""
    parser = argparse.ArgumentParser(description="Sprint J CLIåw")
    subparsers = parser.add_subparsers(dest="command", help="ï(}ä")

    # list-skills}ä
    list_parser = subparsers.add_parser("list-skills", help="ú€ı")
    list_parser.add_argument("--host", help="	ßÇä")
    list_parser.add_argument("--status", default="prod", help="	¶Çä")

    # mine}ä
    mine_parser = subparsers.add_parser("mine", help="˜€ı!")
    mine_parser.add_argument("--host", help="îßÇä")
    mine_parser.add_argument("--goal", help="îû¡Çä")
    mine_parser.add_argument("--min-support", type=int, default=10, help=" /¦")
    mine_parser.add_argument("--max-length", type=int, default=5, help=" '!¦")
    mine_parser.add_argument("--min-reward", type=float, default=0.7, help=" V±<")
    mine_parser.add_argument("--start-date", help=" Ëå")
    mine_parser.add_argument("--end-date", help="Ó_å")
    mine_parser.add_argument("--output-dir", default="skills/defs", help="“úîU")

    # pack}ä
    pack_parser = subparsers.add_parser("pack", help="S€ı")
    pack_parser.add_argument("skill_yaml", help="€ıYAML‡ö")
    pack_parser.add_argument("-o", "--output", help="“ú‡öï„")
    pack_parser.add_argument("--resources", help="D‡öh÷”	")
    pack_parser.add_argument("--metadata", help="CpnJSON<	")

    # publish}ä
    publish_parser = subparsers.add_parser("publish", help="Ñ€ı")
    publish_parser.add_argument("skill_yaml", help="€ıYAML‡ö")

    # install}ä
    install_parser = subparsers.add_parser("install", help="‰Å€ı")
    install_parser.add_argument("name", help="€ığ")
    install_parser.add_argument("version", help="H,÷")
    install_parser.add_argument("--host", help="îß")
    install_parser.add_argument("--device-id", default="default", help="¾ID")

    # dashboard}ä
    dashboard_parser = subparsers.add_parser("dashboard", help="Ñ§êhØ")
    dashboard_parser.add_argument("--days", type=int, default=7, help="ß¡)p")
    dashboard_parser.add_argument("--host", help="	ßÇä")

    # errors}ä
    errors_parser = subparsers.add_parser("errors", help="ï")
    errors_parser.add_argument("--days", type=int, default=7, help="ß¡)p")
    errors_parser.add_argument("--skill", help="€ığÇä")
    errors_parser.add_argument("--limit", type=int, default=20, help=">:pÏ")

    # real-time}ä
    realtime_parser = subparsers.add_parser("real-time", help="ö")
    realtime_parser.add_argument("--limit", type=int, default=50, help=">:pÏ")

    # registry}ä
    registry_parser = subparsers.add_parser("registry", help="èŒháo")

    # test-macro}ä
    test_parser = subparsers.add_parser("test-macro", help="KÕ")
    test_parser.add_argument("name", help="ğ")
    test_parser.add_argument("--version", help="H,÷")
    test_parser.add_argument("--verbose", action="store_true", help="æÆ“ú")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = SprintJCLI()

    # gL}ä
    try:
        if args.command == "list-skills":
            asyncio.run(cli.list_skills_command(args))
        elif args.command == "mine":
            asyncio.run(cli.mine_skills_command(args))
        elif args.command == "pack":
            asyncio.run(cli.pack_skill_command(args))
        elif args.command == "publish":
            asyncio.run(cli.publish_skill_command(args))
        elif args.command == "install":
            asyncio.run(cli.install_skill_command(args))
        elif args.command == "dashboard":
            asyncio.run(cli.dashboard_command(args))
        elif args.command == "errors":
            asyncio.run(cli.errors_command(args))
        elif args.command == "real-time":
            asyncio.run(cli.real_time_command(args))
        elif args.command == "registry":
            asyncio.run(cli.registry_info_command(args))
        elif args.command == "test-macro":
            asyncio.run(cli.test_macro_command(args))
    except KeyboardInterrupt:
        print("\nÍ\òÖˆ")
    except Exception as e:
        logger.error(f"}ägL1%: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()