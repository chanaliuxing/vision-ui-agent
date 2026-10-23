"""
Sprint K: ê”gLÎ
9nubB¦†òŸ‡(7O}¨tgLVeŒÂp
"""

import asyncio
import json
import logging
import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta

from vision.services.multimodal_fusion import PageUnderstanding

logger = logging.getLogger(__name__)

class ExecutionStrategy(Enum):
    """gLVe{‹"""
    CONSERVATIVE = "conservative"    # ÝˆVeØï`'
    AGGRESSIVE = "aggressive"       # ÀÛVeØH‡
    LEARNING = "learning"           # f`Ve¢"°:o
    BALANCED = "balanced"           # saVe-¸¹H
    CUSTOM = "custom"              # êšIVe

class Priority(Enum):
    """(7H§O}"""
    RELIABILITY = "reliability"    # ï`'H
    SPEED = "speed"                # ¦H
    ACCURACY = "accuracy"          # Æn'H
    COST = "cost"                 # ,H

@dataclass
class ExecutionContext:
    """gL
‡"""
    session_id: str
    page_understanding: PageUnderstanding
    user_preferences: Dict[str, Any]
    execution_timeout: int
    error_tolerance: float
    host: str
    goal: str
    previous_attempts: List[Dict[str, Any]]
    resource_constraints: Dict[str, Any]

@dataclass
class StrategyParameters:
    """VeÂp"""
    click_timeout: int = 5000
    scroll_amount: int = 600
    wait_timeout: int = 8000
    retry_count: int = 3
    confidence_threshold: float = 0.7
    element_detection_timeout: int = 10000
    action_delay_ms: int = 500

@dataclass
class ExecutionResult:
    """gLÓœ"""
    success: bool
    strategy_used: ExecutionStrategy
    parameters_used: StrategyParameters
    execution_time_ms: int
    steps_completed: int
    error_message: Optional[str]
    performance_metrics: Dict[str, float]
    learning_signals: Dict[str, Any]

class ContextAnalyzer:
    """
‡h"""

    def __init__(self):
        self.complexity_weights = {
            'element_count': 0.3,
            'layout_complexity': 0.2,
            'interaction_zones': 0.2,
            'visual_complexity': 0.15,
            'text_density': 0.15
        }

    def analyze_context(self, context: ExecutionContext) -> Dict[str, float]:
        """
        gL
‡³VàP

        Args:
            context: gL
‡

        Returns:
            Dict[str, float]: àPWx
        """
        try:
            page_understanding = context.page_understanding

            # ubB¦
            page_complexity = self._assess_page_complexity(page_understanding)

            # †òŸ‡
            historical_success_rate = self._get_historical_success_rate(
                context.host, context.goal, context.previous_attempts
            )

            # (7O}
            user_priority = self._analyze_user_priority(context.user_preferences)

            # öô¦_
            time_pressure = self._assess_time_pressure(context.execution_timeout)

            # ï¹Í¦
            error_tolerance = context.error_tolerance

            # D¦_
            resource_pressure = self._assess_resource_constraints(context.resource_constraints)

            factors = {
                'page_complexity': page_complexity,
                'historical_success_rate': historical_success_rate,
                'user_priority_reliability': 1.0 if user_priority == Priority.RELIABILITY else 0.0,
                'user_priority_speed': 1.0 if user_priority == Priority.SPEED else 0.0,
                'user_priority_accuracy': 1.0 if user_priority == Priority.ACCURACY else 0.0,
                'time_pressure': time_pressure,
                'error_tolerance': error_tolerance,
                'resource_pressure': resource_pressure,
                'previous_failures': len([a for a in context.previous_attempts if not a.get('success', False)]) / max(len(context.previous_attempts), 1)
            }

            logger.debug(f"
‡Œ: {factors}")
            return factors

        except Exception as e:
            logger.error(f"
‡1%: {e}")
            return self._get_default_factors()

    def _assess_page_complexity(self, page_understanding: PageUnderstanding) -> float:
        """Ä0ubB¦"""
        try:
            # C pÏB¦
            element_count = len(page_understanding.interaction_zones)
            element_complexity = min(1.0, element_count / 20.0)

            # @B¦
            layout_complexity = page_understanding.visual_features.visual_complexity

            # ¤’:ßB¦
            interaction_complexity = len(page_understanding.primary_actions) / 5.0

            # ÆÉB¦
            visual_complexity = page_understanding.visual_features.visual_complexity

            # ‡,Æ¦
            text_density = page_understanding.text_features.text_density / 100.0

            #  C¡—;B¦
            total_complexity = (
                element_complexity * self.complexity_weights['element_count'] +
                layout_complexity * self.complexity_weights['layout_complexity'] +
                interaction_complexity * self.complexity_weights['interaction_zones'] +
                visual_complexity * self.complexity_weights['visual_complexity'] +
                text_density * self.complexity_weights['text_density']
            )

            return min(1.0, total_complexity)

        except Exception as e:
            logger.warning(f"ubB¦Ä01%: {e}")
            return 0.5

    def _get_historical_success_rate(self, host: str, goal: str, previous_attempts: List[Dict]) -> float:
        """·Ö†òŸ‡"""
        if not previous_attempts:
            return 0.5  # Ø¤Ÿ‡

        successful_attempts = sum(1 for attempt in previous_attempts if attempt.get('success', False))
        total_attempts = len(previous_attempts)

        return successful_attempts / total_attempts if total_attempts > 0 else 0.5

    def _analyze_user_priority(self, user_preferences: Dict[str, Any]) -> Priority:
        """(7H§O}"""
        priority_str = user_preferences.get('priority', 'balanced')

        try:
            return Priority(priority_str)
        except ValueError:
            return Priority.RELIABILITY

    def _assess_time_pressure(self, execution_timeout: int) -> float:
        """Ä0öô‹›"""
        # Æ…ööô:30Ò
        standard_timeout = 30000

        if execution_timeout <= 0:
            return 0.5

        # …ööôŠíöô‹›Š'
        pressure = 1.0 - min(1.0, execution_timeout / standard_timeout)
        return pressure

    def _assess_resource_constraints(self, resource_constraints: Dict[str, Any]) -> float:
        """Ä0D¦_"""
        if not resource_constraints:
            return 0.0

        # ÀåCPU…XQÜID¦_
        cpu_usage = resource_constraints.get('cpu_usage', 0.0)
        memory_usage = resource_constraints.get('memory_usage', 0.0)
        network_latency = resource_constraints.get('network_latency', 0.0)

        # €„D‹›¡—
        pressure = (cpu_usage + memory_usage + min(1.0, network_latency / 1000)) / 3
        return min(1.0, pressure)

    def _get_default_factors(self) -> Dict[str, float]:
        """·ÖØ¤àP"""
        return {
            'page_complexity': 0.5,
            'historical_success_rate': 0.5,
            'user_priority_reliability': 0.0,
            'user_priority_speed': 0.0,
            'user_priority_accuracy': 0.0,
            'time_pressure': 0.5,
            'error_tolerance': 0.5,
            'resource_pressure': 0.0,
            'previous_failures': 0.0
        }

class StrategySelector:
    """Ve	éh"""

    def __init__(self):
        self.strategy_weights = self._initialize_strategy_weights()

    def _initialize_strategy_weights(self) -> Dict[ExecutionStrategy, Dict[str, float]]:
        """ËVeCÍé5"""
        return {
            ExecutionStrategy.CONSERVATIVE: {
                'page_complexity': -0.8,      # BuböCÍMN
                'historical_success_rate': 0.6,  # Ÿ‡ØöCÍž 
                'user_priority_reliability': 0.9,  # ï`'HöCÍØ
                'user_priority_speed': -0.5,      # ¦HöCÍMN
                'time_pressure': -0.4,            # öô‹›öCÍMN
                'error_tolerance': -0.3,          # ï¹Í¦NöCÍØ
                'resource_pressure': 0.2,         # D' ö®OÝˆ
                'previous_failures': 0.7          # KM1%öCÍž 
            },
            ExecutionStrategy.AGGRESSIVE: {
                'page_complexity': -0.3,          # BuböCÍeMN
                'historical_success_rate': 0.4,   # Ÿ‡qÍƒ
                'user_priority_reliability': -0.7, # ï`'HöCÍMN
                'user_priority_speed': 0.9,       # ¦HöCÍØ
                'time_pressure': 0.8,             # öô‹›öCÍž 
                'error_tolerance': 0.2,           # ï¹Í¦qÍƒ
                'resource_pressure': -0.4,        # D' öCÍMN
                'previous_failures': -0.3         # KM1%öCÍMN
            },
            ExecutionStrategy.LEARNING: {
                'page_complexity': 0.3,           # BuböCÍž ¢":	
                'historical_success_rate': -0.2,  # Ÿ‡NöCÍž  f`	
                'user_priority_reliability': -0.2,
                'user_priority_speed': -0.2,
                'time_pressure': -0.6,            # öô‹›öCÍMN
                'error_tolerance': 0.4,           # ï¹Í¦ØöCÍž 
                'resource_pressure': -0.1,
                'previous_failures': 0.2          # 1%ïåÕf`
            },
            ExecutionStrategy.BALANCED: {
                'page_complexity': 0.0,           # -'
                'historical_success_rate': 0.2,
                'user_priority_reliability': 0.1,
                'user_priority_speed': 0.1,
                'time_pressure': 0.0,
                'error_tolerance': 0.0,
                'resource_pressure': 0.0,
                'previous_failures': 0.1
            }
        }

    def select_strategy(self, context_factors: Dict[str, float]) -> Tuple[ExecutionStrategy, float]:
        """
        9n
‡àP	é Ve

        Args:
            context_factors: 
‡àP

        Returns:
            Tuple[ExecutionStrategy, float]: 	-„VeŒná¦
        """
        try:
            strategy_scores = {}

            # ¡—Ï*Ve„—
            for strategy, weights in self.strategy_weights.items():
                score = 0.0
                for factor, value in context_factors.items():
                    weight = weights.get(factor, 0.0)
                    score += weight * value

                strategy_scores[strategy] = score

            # 	é— Ø„Ve
            best_strategy = max(strategy_scores, key=strategy_scores.get)
            best_score = strategy_scores[best_strategy]

            # ¡—ná¦úŽ—î	
            scores = list(strategy_scores.values())
            scores.sort(reverse=True)

            if len(scores) > 1:
                confidence = (scores[0] - scores[1]) / (max(abs(scores[0]), abs(scores[1]), 0.1))
                confidence = min(1.0, max(0.1, (confidence + 1) / 2))  # R 0 [0.1, 1.0]
            else:
                confidence = 0.5

            logger.info(f"Ve	é: {best_strategy.value}, ná¦: {confidence:.3f}")
            logger.debug(f"Ve—: {strategy_scores}")

            return best_strategy, confidence

        except Exception as e:
            logger.error(f"Ve	é1%: {e}")
            return ExecutionStrategy.BALANCED, 0.5

class ParameterOptimizer:
    """Âph"""

    def __init__(self):
        self.base_parameters = {
            ExecutionStrategy.CONSERVATIVE: StrategyParameters(
                click_timeout=8000,
                scroll_amount=400,
                wait_timeout=12000,
                retry_count=5,
                confidence_threshold=0.8,
                element_detection_timeout=15000,
                action_delay_ms=1000
            ),
            ExecutionStrategy.AGGRESSIVE: StrategyParameters(
                click_timeout=3000,
                scroll_amount=800,
                wait_timeout=5000,
                retry_count=2,
                confidence_threshold=0.5,
                element_detection_timeout=6000,
                action_delay_ms=200
            ),
            ExecutionStrategy.LEARNING: StrategyParameters(
                click_timeout=6000,
                scroll_amount=600,
                wait_timeout=10000,
                retry_count=4,
                confidence_threshold=0.6,
                element_detection_timeout=12000,
                action_delay_ms=800
            ),
            ExecutionStrategy.BALANCED: StrategyParameters(
                click_timeout=5000,
                scroll_amount=600,
                wait_timeout=8000,
                retry_count=3,
                confidence_threshold=0.7,
                element_detection_timeout=10000,
                action_delay_ms=500
            )
        }

    def optimize_parameters(
        self,
        strategy: ExecutionStrategy,
        context_factors: Dict[str, float],
        context: ExecutionContext
    ) -> StrategyParameters:
        """
        gLÂp

        Args:
            strategy: 	é„Ve
            context_factors: 
‡àP
            context: gL
‡

        Returns:
            StrategyParameters: „Âp
        """
        try:
            # ·Öú@Âp
            base_params = self.base_parameters.get(strategy, self.base_parameters[ExecutionStrategy.BALANCED])

            # úŽ
‡àPtÂp
            optimized_params = self._adjust_parameters_by_context(base_params, context_factors, context)

            # úŽ†òpnÛLö¯€ž°	
            optimized_params = self._bayesian_optimization(optimized_params, context)

            logger.info(f"ÂpŒ: {strategy.value}")
            logger.debug(f"Âp: {asdict(optimized_params)}")

            return optimized_params

        except Exception as e:
            logger.error(f"Âp1%: {e}")
            return self.base_parameters[ExecutionStrategy.BALANCED]

    def _adjust_parameters_by_context(
        self,
        base_params: StrategyParameters,
        context_factors: Dict[str, float],
        context: ExecutionContext
    ) -> StrategyParameters:
        """úŽ
‡tÂp"""
        adjusted_params = StrategyParameters(
            click_timeout=base_params.click_timeout,
            scroll_amount=base_params.scroll_amount,
            wait_timeout=base_params.wait_timeout,
            retry_count=base_params.retry_count,
            confidence_threshold=base_params.confidence_threshold,
            element_detection_timeout=base_params.element_detection_timeout,
            action_delay_ms=base_params.action_delay_ms
        )

        # 9nubB¦t
        complexity = context_factors.get('page_complexity', 0.5)
        if complexity > 0.7:
            adjusted_params.click_timeout = int(adjusted_params.click_timeout * 1.3)
            adjusted_params.wait_timeout = int(adjusted_params.wait_timeout * 1.2)
            adjusted_params.element_detection_timeout = int(adjusted_params.element_detection_timeout * 1.2)

        # 9nöô‹›t
        time_pressure = context_factors.get('time_pressure', 0.5)
        if time_pressure > 0.6:
            adjusted_params.click_timeout = int(adjusted_params.click_timeout * 0.8)
            adjusted_params.wait_timeout = int(adjusted_params.wait_timeout * 0.7)
            adjusted_params.action_delay_ms = int(adjusted_params.action_delay_ms * 0.5)

        # 9n†òŸ‡t
        success_rate = context_factors.get('historical_success_rate', 0.5)
        if success_rate < 0.3:
            adjusted_params.retry_count = min(6, adjusted_params.retry_count + 2)
            adjusted_params.confidence_threshold = max(0.4, adjusted_params.confidence_threshold - 0.1)

        # 9nï¹Í¦t
        error_tolerance = context_factors.get('error_tolerance', 0.5)
        if error_tolerance < 0.3:
            adjusted_params.retry_count = min(8, adjusted_params.retry_count + 1)
            adjusted_params.confidence_threshold = min(0.9, adjusted_params.confidence_threshold + 0.1)

        # nÝÂp(ô…
        adjusted_params = self._clamp_parameters(adjusted_params)

        return adjusted_params

    def _bayesian_optimization(self, params: StrategyParameters, context: ExecutionContext) -> StrategyParameters:
        """ö¯€ž°	"""
        # ÙÌ”åž°úŽ†òpn„ö¯
        # îMÔÞúŽÏŒt„Âp

        if context.previous_attempts:
            # KMÕ„ÓœtÂp
            failed_attempts = [a for a in context.previous_attempts if not a.get('success', False)]

            if len(failed_attempts) > 2:
                # !1%ž Ýˆ'
                params.click_timeout = int(params.click_timeout * 1.2)
                params.retry_count = min(6, params.retry_count + 1)
                params.confidence_threshold = min(0.85, params.confidence_threshold + 0.05)

        return params

    def _clamp_parameters(self, params: StrategyParameters) -> StrategyParameters:
        """nÝÂp(ô…"""
        return StrategyParameters(
            click_timeout=max(1000, min(20000, params.click_timeout)),
            scroll_amount=max(100, min(2000, params.scroll_amount)),
            wait_timeout=max(2000, min(30000, params.wait_timeout)),
            retry_count=max(1, min(8, params.retry_count)),
            confidence_threshold=max(0.1, min(0.95, params.confidence_threshold)),
            element_detection_timeout=max(3000, min(30000, params.element_detection_timeout)),
            action_delay_ms=max(0, min(3000, params.action_delay_ms))
        )

class ExecutionMonitor:
    """gLÑ§h"""

    def __init__(self):
        self.monitoring_interval = 0.5  # Ñ§ô”Ò	
        self.anomaly_threshold = 0.7    # 8ÀK<

    async def monitor_execution(
        self,
        execution_task: asyncio.Task,
        context: ExecutionContext,
        strategy: ExecutionStrategy,
        parameters: StrategyParameters,
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        žöÑ§gLÇ

        Args:
            execution_task: gLû¡
            context: gL
‡
            strategy: („Ve
            parameters: („Âp
            callback: Ñ§Þýp

        Returns:
            Dict[str, Any]: Ñ§Óœ
        """
        monitoring_data = {
            'start_time': time.time(),
            'strategy': strategy.value,
            'parameters': asdict(parameters),
            'metrics': [],
            'anomalies': [],
            'adjustments': []
        }

        try:
            while not execution_task.done():
                await asyncio.sleep(self.monitoring_interval)

                # 6ÆSM
                current_metrics = await self._collect_current_metrics(execution_task, context)
                monitoring_data['metrics'].append(current_metrics)

                # 8ÀK
                anomaly = self._detect_anomaly(current_metrics, monitoring_data['metrics'])
                if anomaly:
                    monitoring_data['anomalies'].append(anomaly)

                    # æÑt
                    adjustment = await self._calculate_adjustment(anomaly, context, parameters)
                    if adjustment:
                        monitoring_data['adjustments'].append(adjustment)

                        # Þå
                        if callback:
                            await callback(adjustment)

                # „KgLÓœ
                prediction = self._predict_execution_outcome(monitoring_data['metrics'])
                if prediction['success_probability'] < 0.2:
                    # Ÿ‚‡*Nú®Èb
                    monitoring_data['early_termination_suggested'] = True
                    break

            # gLŒ6Æ ÈÓœ
            monitoring_data['end_time'] = time.time()
            monitoring_data['total_duration'] = monitoring_data['end_time'] - monitoring_data['start_time']

            return monitoring_data

        except Exception as e:
            logger.error(f"gLÑ§1%: {e}")
            return monitoring_data

    async def _collect_current_metrics(self, execution_task: asyncio.Task, context: ExecutionContext) -> Dict[str, float]:
        """6ÆSMgL"""
        current_time = time.time()

        # ú@
        metrics = {
            'timestamp': current_time,
            'memory_usage': 0.0,  # ÙÌ”åžEKÏ…X(
            'cpu_usage': 0.0,    # ÙÌ”åžEKÏCPU(
            'network_latency': 0.0,  # ÙÌ”åžEKÏQÜöß
            'execution_progress': 0.5  # ÙÌ”åžE¡—gLÛ¦
        }

        # û¡¶
        if hasattr(execution_task, '_state'):
            metrics['task_state'] = execution_task._state
        else:
            metrics['task_state'] = 'running'

        return metrics

    def _detect_anomaly(self, current_metrics: Dict[str, float], historical_metrics: List[Dict[str, float]]) -> Optional[Dict[str, Any]]:
        """ÀKgL8"""
        if len(historical_metrics) < 3:
            return None

        # €„8ÀK;‘
        recent_metrics = historical_metrics[-3:]

        # ÀK…X(8
        current_memory = current_metrics.get('memory_usage', 0.0)
        avg_memory = np.mean([m.get('memory_usage', 0.0) for m in recent_metrics])

        if current_memory > avg_memory * 2 and current_memory > self.anomaly_threshold:
            return {
                'type': 'high_memory_usage',
                'current_value': current_memory,
                'expected_value': avg_memory,
                'severity': 'medium',
                'timestamp': current_metrics['timestamp']
            }

        # ÀKgLöô8
        if len(historical_metrics) > 0:
            time_diff = current_metrics['timestamp'] - historical_metrics[0]['timestamp']
            if time_diff > 30:  # gL…Ç30Ò
                return {
                    'type': 'execution_timeout',
                    'current_value': time_diff,
                    'expected_value': 15,
                    'severity': 'high',
                    'timestamp': current_metrics['timestamp']
                }

        return None

    async def _calculate_adjustment(
        self,
        anomaly: Dict[str, Any],
        context: ExecutionContext,
        current_parameters: StrategyParameters
    ) -> Optional[Dict[str, Any]]:
        """¡—tú®"""
        adjustment_type = anomaly['type']

        if adjustment_type == 'high_memory_usage':
            return {
                'type': 'reduce_concurrency',
                'reason': 'high_memory_usage',
                'suggested_parameters': {
                    'action_delay_ms': current_parameters.action_delay_ms + 200
                }
            }

        elif adjustment_type == 'execution_timeout':
            return {
                'type': 'increase_timeouts',
                'reason': 'execution_timeout',
                'suggested_parameters': {
                    'click_timeout': int(current_parameters.click_timeout * 1.5),
                    'wait_timeout': int(current_parameters.wait_timeout * 1.3)
                }
            }

        return None

    def _predict_execution_outcome(self, metrics_history: List[Dict[str, float]]) -> Dict[str, float]:
        """„KgLÓœ"""
        if len(metrics_history) < 2:
            return {'success_probability': 0.5}

        # €„„K;‘
        recent_progress = [m.get('execution_progress', 0.5) for m in metrics_history[-3:]]
        avg_progress = np.mean(recent_progress)

        # úŽÛ¦Œ‹¿„KŸ‚‡
        if len(recent_progress) > 1:
            progress_trend = recent_progress[-1] - recent_progress[0]
            if progress_trend > 0 and avg_progress > 0.3:
                success_probability = min(0.9, 0.5 + avg_progress)
            else:
                success_probability = max(0.1, avg_progress)
        else:
            success_probability = avg_progress

        return {
            'success_probability': success_probability,
            'estimated_completion_time': 30 - (30 * avg_progress)  # €0¡
        }

class AdaptiveExecutionEngine:
    """ê”gLÎ"""

    def __init__(self):
        self.context_analyzer = ContextAnalyzer()
        self.strategy_selector = StrategySelector()
        self.parameter_optimizer = ParameterOptimizer()
        self.execution_monitor = ExecutionMonitor()

    async def execute_adaptive(
        self,
        context: ExecutionContext,
        execution_function: Callable,
        monitor_callback: Optional[Callable] = None
    ) -> ExecutionResult:
        """
        ê”gL

        Args:
            context: gL
‡
            execution_function: žEgLýp
            monitor_callback: Ñ§Þýp

        Returns:
            ExecutionResult: gLÓœ
        """
        start_time = time.time()

        try:
            # 1. gL
‡
            context_factors = self.context_analyzer.analyze_context(context)

            # 2. 	égLVe
            strategy, strategy_confidence = self.strategy_selector.select_strategy(context_factors)

            # 3. gLÂp
            optimized_parameters = self.parameter_optimizer.optimize_parameters(
                strategy, context_factors, context
            )

            # 4. úgLû¡
            execution_task = asyncio.create_task(
                execution_function(context, strategy, optimized_parameters)
            )

            # 5. Ñ§gLÇ
            monitoring_data = await self.execution_monitor.monitor_execution(
                execution_task, context, strategy, optimized_parameters, monitor_callback
            )

            # 6. ·ÖgLÓœ
            execution_result = await execution_task
            execution_time = int((time.time() - start_time) * 1000)

            # 7. f`á÷
            learning_signals = self._generate_learning_signals(
                context_factors, strategy, optimized_parameters, execution_result, monitoring_data
            )

            # 8. „úÓœ
            result = ExecutionResult(
                success=execution_result.get('success', False),
                strategy_used=strategy,
                parameters_used=optimized_parameters,
                execution_time_ms=execution_time,
                steps_completed=execution_result.get('steps_completed', 0),
                error_message=execution_result.get('error_message'),
                performance_metrics={
                    'strategy_confidence': strategy_confidence,
                    'monitoring_anomalies': len(monitoring_data.get('anomalies', [])),
                    'monitoring_adjustments': len(monitoring_data.get('adjustments', [])),
                    'context_complexity': context_factors.get('page_complexity', 0.5)
                },
                learning_signals=learning_signals
            )

            logger.info(f"ê”gLŒ: Ÿ={result.success}, Ve={strategy.value}, ö={execution_time}ms")
            return result

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"ê”gL1%: {e}")

            return ExecutionResult(
                success=False,
                strategy_used=ExecutionStrategy.BALANCED,
                parameters_used=self.parameter_optimizer.base_parameters[ExecutionStrategy.BALANCED],
                execution_time_ms=execution_time,
                steps_completed=0,
                error_message=str(e),
                performance_metrics={},
                learning_signals={}
            )

    def _generate_learning_signals(
        self,
        context_factors: Dict[str, float],
        strategy: ExecutionStrategy,
        parameters: StrategyParameters,
        execution_result: Dict[str, Any],
        monitoring_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """f`á÷"""
        return {
            'context_factors': context_factors,
            'strategy_effectiveness': {
                'strategy': strategy.value,
                'success': execution_result.get('success', False),
                'execution_time': execution_result.get('execution_time_ms', 0)
            },
            'parameter_performance': {
                'parameters': asdict(parameters),
                'anomalies_detected': len(monitoring_data.get('anomalies', [])),
                'adjustments_needed': len(monitoring_data.get('adjustments', []))
            },
            'optimization_opportunities': monitoring_data.get('adjustments', []),
            'timestamp': datetime.now().isoformat()
        }

# (:‹
if __name__ == "__main__":
    import asyncio
    from vision.services.multimodal_fusion import PageUnderstanding, PageType

    async def mock_execution_function(context, strategy, parameters):
        """!ßgLýp"""
        await asyncio.sleep(2)  # !ßgLöô
        return {
            'success': True,
            'steps_completed': 5,
            'execution_time_ms': 2000
        }

    async def test_adaptive_execution():
        """KÕê”gL"""
        # ú!ß„gL
‡
        mock_understanding = PageUnderstanding(
            page_id="test_page",
            page_type=PageType.LIST_PAGE,
            confidence=0.8,
            layout=None,
            visual_features=None,
            text_features=None,
            geometric_features=None,
            interaction_zones=[],
            primary_actions=['click', 'scroll'],
            navigation_structure={},
            created_at=datetime.now(),
            fusion_version="1.0.0"
        )

        context = ExecutionContext(
            session_id="test_session",
            page_understanding=mock_understanding,
            user_preferences={'priority': 'reliability'},
            execution_timeout=15000,
            error_tolerance=0.3,
            host="test.com",
            goal="test_goal",
            previous_attempts=[],
            resource_constraints={}
        )

        # úgLÎ
        engine = AdaptiveExecutionEngine()

        # gLê”gL
        result = await engine.execute_adaptive(context, mock_execution_function)

        print(f"gLÓœ: Ÿ={result.success}")
        print(f"(Ve: {result.strategy_used.value}")
        print(f"gLöô: {result.execution_time_ms}ms")
        print(f"'ý: {result.performance_metrics}")

    # ÐLKÕ
    asyncio.run(test_adaptive_execution())