# core/costs.py - Budget counters + policies + degradations
import time
import os
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Budget:
    """Cost budgets and limits for LLM usage and performance"""
    max_strategy_calls: int = 3
    max_picker_calls: int = 5
    max_arbiter_calls: int = 3
    max_tokens_per_run: int = 40000
    max_tokens_per_step: int = 3000
    p95_step_time_ms: int = 5000
    
    @classmethod
    def from_env(cls) -> 'Budget':
        """Load budget from environment variables"""
        return cls(
            max_strategy_calls=int(os.getenv("BGT_MAX_STRATEGY_CALLS", "3")),
            max_picker_calls=int(os.getenv("BGT_MAX_PICKER_CALLS", "5")),
            max_arbiter_calls=int(os.getenv("BGT_MAX_ARBITER_CALLS", "3")),
            max_tokens_per_run=int(os.getenv("BGT_MAX_TOKENS_PER_RUN", "40000")),
            max_tokens_per_step=int(os.getenv("BGT_MAX_TOKENS_PER_STEP", "3000")),
            p95_step_time_ms=int(os.getenv("BGT_P95_STEP_TIME_MS", "5000"))
        )

@dataclass
class Usage:
    """Current usage tracking"""
    strategy_calls: int = 0
    picker_calls: int = 0
    arbiter_calls: int = 0
    tokens: int = 0
    step_tokens: int = 0  # Reset per step
    step_start_ts: float = 0.0
    step_durations_ms: List[int] = field(default_factory=list)
    
    def reset_step(self):
        """Reset step-level counters"""
        self.step_tokens = 0
        self.step_start_ts = 0.0

class CostGuard:
    """Budget enforcement and usage tracking"""
    
    def __init__(self, budget: Budget = None):
        self.bgt = budget or Budget.from_env()
        self.u = Usage()
        self.degradation_count = 0
        self.skip_count = 0
    
    def begin_step(self):
        """Start tracking a new step"""
        self.u.step_start_ts = time.time()
        self.u.reset_step()
    
    def end_step(self):
        """End step tracking and record duration"""
        if self.u.step_start_ts:
            dt = int((time.time() - self.u.step_start_ts) * 1000)
            self.u.step_durations_ms.append(dt)
            self.u.step_start_ts = 0.0
    
    def add_tokens(self, n: int):
        """Add token usage to both step and run totals"""
        tokens = int(n)
        self.u.tokens += tokens
        self.u.step_tokens += tokens
    
    def inc(self, kind: str):
        """Increment call counter for LLM type"""
        if kind == "strategy":
            self.u.strategy_calls += 1
        elif kind == "picker":
            self.u.picker_calls += 1
        elif kind == "arbiter":
            self.u.arbiter_calls += 1
    
    def over_step_budget(self) -> bool:
        """Check if current step is over token budget"""
        return self.u.step_tokens > self.bgt.max_tokens_per_step
    
    def over_run_budget(self) -> bool:
        """Check if run is over total token budget"""
        return self.u.tokens > self.bgt.max_tokens_per_run
    
    def can_call(self, kind: str) -> bool:
        """Check if we can make another LLM call of this type"""
        if kind == "strategy":
            return self.u.strategy_calls < self.bgt.max_strategy_calls
        elif kind == "picker":
            return self.u.picker_calls < self.bgt.max_picker_calls
        elif kind == "arbiter":
            return self.u.arbiter_calls < self.bgt.max_arbiter_calls
        return False
    
    def should_degrade(self, kind: str) -> str:
        """Determine degradation policy for LLM call"""
        if self.over_run_budget():
            return "skip"
        elif self.over_step_budget():
            if kind in ["picker", "arbiter"]:
                return "downscale"
            else:
                return "skip"
        return "none"
    
    def apply_degradation(self, degradation: str):
        """Record that degradation was applied"""
        if degradation in ["downscale", "textonly"]:
            self.degradation_count += 1
        elif degradation == "skip":
            self.skip_count += 1
    
    def get_stats(self) -> dict:
        """Get current usage statistics"""
        durations = self.u.step_durations_ms
        p95_ms = 0
        avg_tokens_per_step = 0
        
        if durations:
            durations.sort()
            p95_idx = int(len(durations) * 0.95)
            p95_ms = durations[p95_idx] if p95_idx < len(durations) else durations[-1]
        
        total_steps = len(durations)
        if total_steps > 0:
            avg_tokens_per_step = self.u.tokens / total_steps
        
        return {
            "strategy_calls": self.u.strategy_calls,
            "picker_calls": self.u.picker_calls,
            "arbiter_calls": self.u.arbiter_calls,
            "total_tokens": self.u.tokens,
            "avg_tokens_per_step": avg_tokens_per_step,
            "p95_step_time_ms": p95_ms,
            "total_steps": total_steps,
            "degradation_count": self.degradation_count,
            "skip_count": self.skip_count,
            "budget_utilization": {
                "strategy": self.u.strategy_calls / self.bgt.max_strategy_calls,
                "picker": self.u.picker_calls / self.bgt.max_picker_calls,
                "arbiter": self.u.arbiter_calls / self.bgt.max_arbiter_calls,
                "tokens": self.u.tokens / self.bgt.max_tokens_per_run
            }
        }

class ImageDegradationPolicy:
    """Policies for degrading image processing to save tokens"""
    
    def __init__(self):
        self.overlay_max_px = int(os.getenv("OVERLAY_MAX_PX", "1024"))
        self.overlay_max_px_fallback = int(os.getenv("OVERLAY_MAX_PX_FALLBACK", "800"))
        self.picker_topk_roi = int(os.getenv("PICKER_TOPK_ROI", "12"))
        self.roi_padding_px = int(os.getenv("ROI_PADDING_PX", "16"))
        self.arbiter_thumb_px = int(os.getenv("ARBITER_THUMB_PX", "96"))
    
    def get_picker_policy(self, degradation: str) -> dict:
        """Get picker image policy based on degradation level"""
        if degradation == "skip":
            return {"allow": False}
        elif degradation == "downscale":
            return {
                "allow": True,
                "max_px": self.overlay_max_px_fallback,
                "crop_to_roi": True,
                "topk_candidates": self.picker_topk_roi,
                "roi_padding": self.roi_padding_px
            }
        else:  # none
            return {
                "allow": True,
                "max_px": self.overlay_max_px,
                "crop_to_roi": False,
                "topk_candidates": None,
                "roi_padding": self.roi_padding_px
            }
    
    def get_arbiter_policy(self, degradation: str) -> dict:
        """Get arbiter image policy based on degradation level"""
        if degradation == "skip":
            return {"allow": False}
        elif degradation == "textonly":
            return {
                "allow": False,  # Text-only mode
                "use_thumbnails": True,
                "thumb_size": self.arbiter_thumb_px
            }
        else:  # none
            return {
                "allow": True,
                "max_px": self.overlay_max_px,
                "use_thumbnails": False
            }
    
    def estimate_tokens(self, kind: str, degradation: str, has_image: bool = True) -> int:
        """Estimate token usage for different LLM calls"""
        base_tokens = {
            "strategy": 800,   # Text-only, compact context
            "picker": 1200,    # Vision + detection list
            "arbiter": 600     # Verification task
        }
        
        tokens = base_tokens.get(kind, 500)
        
        if has_image and kind in ["picker", "arbiter"]:
            if degradation == "downscale":
                tokens += 800  # Smaller image
            elif degradation == "textonly":
                tokens += 200  # Thumbnails or text description
            elif degradation == "none":
                tokens += 1500  # Full image
        
        return tokens