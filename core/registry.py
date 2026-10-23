from typing import Callable, Dict
_ACTIONS: Dict[str, Callable] = {}

def register_action(name: str):
    def deco(fn: Callable):
        _ACTIONS[name] = fn
        return fn
    return deco

def get_action(name: str) -> Callable:
    if name not in _ACTIONS:
        raise KeyError(f"Action '{name}' not registered")
    return _ACTIONS[name]