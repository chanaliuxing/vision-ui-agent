#!/usr/bin/env python3
"""
Action Engine - Stage 0-1 Implementation
Core action registration and execution system
"""

from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass
import inspect
import logging

logger = logging.getLogger(__name__)

@dataclass
class ActionContext:
    """Context passed to action handlers"""
    workflow_state: Dict[str, Any]
    action_params: Dict[str, Any]
    services: Optional[Any] = None
    executor: Optional[Any] = None

class ActionEngine:
    """Core action engine with pluggable action registration"""

    def __init__(self):
        self.actions: Dict[str, Callable] = {}
        self._register_builtin_actions()

    def register_action(self, name: str, handler: Callable):
        """Register an action handler"""
        self.actions[name] = handler
        logger.info(f"Registered action: {name}")

    def execute_action(self, action_name: str, context: ActionContext) -> Dict[str, Any]:
        """Execute a registered action"""
        if action_name not in self.actions:
            raise ValueError(f"Unknown action: {action_name}")

        handler = self.actions[action_name]

        # Inspect handler signature to pass appropriate parameters
        sig = inspect.signature(handler)
        params = {}

        if 'context' in sig.parameters:
            params['context'] = context
        if 'params' in sig.parameters:
            params['params'] = context.action_params
        if 'state' in sig.parameters:
            params['state'] = context.workflow_state

        return handler(**params)

    def _register_builtin_actions(self):
        """Register built-in actions"""
        self.register_action('wait', self._wait_action)
        self.register_action('log', self._log_action)
        self.register_action('set_variable', self._set_variable_action)

    def _wait_action(self, context: ActionContext) -> Dict[str, Any]:
        """Built-in wait action"""
        import time
        seconds = context.action_params.get('seconds', 1.0)
        time.sleep(seconds)
        return {'success': True, 'waited': seconds}

    def _log_action(self, context: ActionContext) -> Dict[str, Any]:
        """Built-in log action"""
        message = context.action_params.get('message', 'Log action executed')
        logger.info(message)
        print(f"[LOG] {message}")
        return {'success': True, 'message': message}

    def _set_variable_action(self, context: ActionContext) -> Dict[str, Any]:
        """Built-in set variable action"""
        var_name = context.action_params.get('name')
        var_value = context.action_params.get('value')

        if var_name:
            context.workflow_state[var_name] = var_value
            return {'success': True, 'variable': var_name, 'value': var_value}

        return {'success': False, 'error': 'Variable name not specified'}

    def list_actions(self) -> List[str]:
        """List all registered actions"""
        return list(self.actions.keys())

    def get_action_info(self, action_name: str) -> Dict[str, Any]:
        """Get information about an action"""
        if action_name not in self.actions:
            return {'error': f'Action {action_name} not found'}

        handler = self.actions[action_name]
        sig = inspect.signature(handler)

        return {
            'name': action_name,
            'handler': handler.__name__,
            'parameters': list(sig.parameters.keys()),
            'docstring': handler.__doc__
        }