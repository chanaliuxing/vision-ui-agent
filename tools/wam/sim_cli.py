#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .sim import PageState, simulate


def main():
    ap = argparse.ArgumentParser(description="Dry-run workflow simulation and suggestions")
    ap.add_argument("workflow", help="Path to workflow JSON")
    ap.add_argument("--present", nargs="*", default=[], help="List of selectors or role:text available in DOM")
    ap.add_argument("--no-scroll", action="store_true", help="Disable scroll availability in PageState")
    args = ap.parse_args()

    doc = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    ps = PageState(dom_present=args.present, scrollable=not args.no_scroll)
    rep = simulate(doc, ps)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

