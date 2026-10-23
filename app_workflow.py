from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from pathlib import Path
import json
import re
import time
from typing import Any, Dict, Optional

from core.prompt_builder import build_workflow_prompt
from core.llm_client import generate_json

app = FastAPI(title="Workflow Generation API", version="1.0.0")
router = APIRouter()

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "workflow_generation"}


class WorkflowGenReq(BaseModel):
    task: str
    env: Dict[str, Any] | None = None
    user_inputs: Dict[str, Any] | None = None
    store: bool = True
    flow_name: Optional[str] = None  # e.g., "wechat_autoreply.json"
    temperature: float = 0.2


def _slug(s: str) -> str:
    s2 = re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")
    return s2 or f"flow_{int(time.time())}"


@router.post("/workflow/generate")
def generate_workflow(req: WorkflowGenReq):
    messages = build_workflow_prompt(task=req.task, env=req.env or {}, user_inputs=req.user_inputs or {}, include_examples=True)
    # Provider/model can be selected by env (LLM_PROVIDER/LLM_MODEL) or future request fields
    flow = generate_json(messages=messages, image_path=None, temperature=req.temperature)
    saved = None
    if req.store:
        Path("flows").mkdir(parents=True, exist_ok=True)
        name = req.flow_name or (_slug(req.task)[:60] + ".json")
        path = Path("flows") / name
        path.write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = str(path)
    return {"flow": flow, "file": saved}

app.include_router(router)
