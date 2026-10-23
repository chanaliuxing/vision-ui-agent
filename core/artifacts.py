from pathlib import Path
import shutil, json, time

def run_dir(base: str, run_id: str) -> Path:
    p = Path(base) / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def step_dir(base: str, run_id: str, state: str, step_idx: int) -> Path:
    p = run_dir(base, run_id) / f"{state}_step{step_idx:03d}"
    p.mkdir(parents=True, exist_ok=True)
    return p

def dump_json(p: Path, name: str, obj):
    with open(p / name, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def snapshot_note(p: Path, note: str):
    with open(p / "README.txt", "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + note + "\n")