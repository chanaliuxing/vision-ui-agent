"""
WAM - Workflow Authoring Module
工作流构建器，提供链式API来构建符合JSON Schema的工作流
"""
import json
import copy
from typing import Dict, List, Any, Optional, Union

class WorkflowBuilder:
    """工作流构建器"""

    def __init__(self, version: str = "1.3", name: str = None):
        """初始化工作流构建器"""
        self.doc = {
            "version": version,
            "start": None,
            "vars": {},
            "states": {}
        }
        if name:
            self.doc["name"] = name

    def name(self, name: str) -> 'WorkflowBuilder':
        """设置工作流名称"""
        self.doc["name"] = name
        return self

    def description(self, desc: str) -> 'WorkflowBuilder':
        """设置工作流描述"""
        self.doc["description"] = desc
        return self

    def start(self, state: str) -> 'WorkflowBuilder':
        """设置开始状态"""
        self.doc["start"] = state
        return self

    def set_var(self, key: str, value: Any) -> 'WorkflowBuilder':
        """设置变量"""
        self.doc["vars"][key] = value
        return self

    def set_vars(self, vars_dict: Dict[str, Any]) -> 'WorkflowBuilder':
        """批量设置变量"""
        self.doc["vars"].update(vars_dict)
        return self

    def llm_provider(self, provider: str, model: str = None) -> 'WorkflowBuilder':
        """设置LLM提供商"""
        self.doc["llm_provider"] = provider
        if model:
            self.doc["llm_model"] = model
        return self

    def context(self, context: Dict[str, Any]) -> 'WorkflowBuilder':
        """设置上下文"""
        self.doc["context"] = context
        return self

    def metadata(self, metadata: Dict[str, Any]) -> 'WorkflowBuilder':
        """设置元数据"""
        self.doc["metadata"] = metadata
        return self

    def autofix(self, mode: str = "suggest_only", **config) -> 'WorkflowBuilder':
        """配置自愈功能"""
        autofix_config = {
            "mode": mode
        }
        autofix_config.update(config)
        self.doc["autofix"] = autofix_config
        return self

    def state(self, name: str, actions: List[Dict[str, Any]],
              transitions: Optional[List[Dict[str, Any]]] = None,
              on_success: Optional[str] = None,
              on_error: Optional[str] = None,
              description: Optional[str] = None) -> 'WorkflowBuilder':
        """添加状态"""
        state_def = {"actions": actions}

        if transitions:
            state_def["transitions"] = transitions
        if on_success:
            state_def["on_success"] = on_success
        if on_error:
            state_def["on_error"] = on_error
        if description:
            state_def["description"] = description

        self.doc["states"][name] = state_def

        # 如果没有设置起始状态，自动设置
        if not self.doc["start"]:
            self.start(name)

        return self

    def for_range(self, name: str, counter: str, count_expr: Union[str, int],
                  body_actions: List[Dict[str, Any]],
                  next_state: str = "done") -> 'WorkflowBuilder':
        """创建for循环结构"""
        loop_state = f"{name}_loop"

        # 设置计数器初值
        self.set_var(counter, 0)

        # 创建循环体
        loop_actions = body_actions + [
            {"do": "increment_variable", "name": counter}
        ]

        # 创建循环转换条件
        transitions = [
            {"if": f"@{counter} < {count_expr}", "go_to": loop_state, "else_go_to": next_state}
        ]

        self.state(loop_state, loop_actions, transitions)

        # 如果没有设置起始状态，设置为循环状态
        if not self.doc["start"]:
            self.start(loop_state)

        return self

    def for_list(self, name: str, item_var: str, index_var: str,
                 list_var: str, body_actions: List[Dict[str, Any]],
                 next_state: str = "done") -> 'WorkflowBuilder':
        """创建遍历列表的循环"""
        loop_state = f"{name}_loop"

        # 设置索引初值
        self.set_var(index_var, 0)

        # 获取列表长度
        get_length_actions = [
            {"do": "get_list_length", "from": f"@{list_var}", "save": f"{list_var}_length"}
        ]

        # 循环体：获取当前项 + 执行动作 + 递增索引
        loop_actions = [
            {"do": "get_list_item", "from": f"@{list_var}", "index": f"@{index_var}", "save": item_var}
        ] + body_actions + [
            {"do": "increment_variable", "name": index_var}
        ]

        # 转换条件
        transitions = [
            {"if": f"@{index_var} < @{list_var}_length", "go_to": loop_state, "else_go_to": next_state}
        ]

        # 添加准备状态
        prep_state = f"{name}_prep"
        self.state(prep_state, get_length_actions, on_success=loop_state)
        self.state(loop_state, loop_actions, transitions)

        if not self.doc["start"]:
            self.start(prep_state)

        return self

    def while_loop(self, name: str, condition: str, body_actions: List[Dict[str, Any]],
                   max_iterations: int = 100, next_state: str = "done") -> 'WorkflowBuilder':
        """创建while循环（带最大迭代次数保护）"""
        loop_state = f"{name}_loop"
        counter = f"{name}_counter"

        # 设置计数器
        self.set_var(counter, 0)

        # 循环体 + 计数器递增
        loop_actions = body_actions + [
            {"do": "increment_variable", "name": counter}
        ]

        # 转换条件：主条件 AND 未超过最大迭代次数
        transitions = [
            {"if": f"({condition}) && @{counter} < {max_iterations}", "go_to": loop_state, "else_go_to": next_state}
        ]

        self.state(loop_state, loop_actions, transitions)

        if not self.doc["start"]:
            self.start(loop_state)

        return self

    def poll(self, name: str, period_ms: int, actions: List[Dict[str, Any]],
             max_iterations: Optional[int] = None) -> 'WorkflowBuilder':
        """创建轮询循环"""
        poll_actions = actions + [
            {"do": "sleep_ms", "duration": period_ms}
        ]

        if max_iterations:
            # 有限轮询
            return self.for_range(name, f"{name}_count", max_iterations, poll_actions, "done")
        else:
            # 无限轮询
            self.state(name, poll_actions, on_success=name)
            if not self.doc["start"]:
                self.start(name)
            return self

    def task_sequence(self, name: str, tasks: List[Dict[str, Any]],
                      next_state: str = "done") -> 'WorkflowBuilder':
        """创建任务序列"""
        actions = []
        for i, task in enumerate(tasks):
            task_action = {"do": "task.run"}
            task_action.update(task)
            if "save" not in task_action:
                task_action["save"] = f"task_{i}_result"
            actions.append(task_action)

        self.state(name, actions, on_success=next_state)

        if not self.doc["start"]:
            self.start(name)

        return self

    def parallel_tasks(self, name: str, tasks: List[Dict[str, Any]],
                       wait_for: str = "all", next_state: str = "done") -> 'WorkflowBuilder':
        """创建并行任务执行"""
        # 为每个任务创建独立状态
        task_states = []
        for i, task in enumerate(tasks):
            task_state = f"{name}_task_{i}"
            task_action = {"do": "task.run"}
            task_action.update(task)
            if "save" not in task_action:
                task_action["save"] = f"parallel_task_{i}_result"

            self.state(task_state, [task_action], on_success=f"{name}_sync")
            task_states.append(task_state)

        # 创建同步点（简化实现，实际可能需要更复杂的协调机制）
        sync_actions = [
            {"do": "sleep_ms", "duration": 100}  # 简单等待所有任务完成
        ]
        self.state(f"{name}_sync", sync_actions, on_success=next_state)

        # 创建启动器
        launch_actions = [
            {"do": "sleep_ms", "duration": 10}  # 启动所有任务的占位符
        ]
        self.state(name, launch_actions, on_success=task_states[0])  # 简化：顺序启动

        if not self.doc["start"]:
            self.start(name)

        return self

    def conditional(self, name: str, condition: str,
                    if_actions: List[Dict[str, Any]],
                    else_actions: Optional[List[Dict[str, Any]]] = None,
                    next_state: str = "done") -> 'WorkflowBuilder':
        """创建条件分支"""
        if_state = f"{name}_if"
        else_state = f"{name}_else"

        # 创建条件检查状态
        check_actions = [
            {"do": "sleep_ms", "duration": 1}  # 占位符，实际条件检查逻辑
        ]

        transitions = [
            {"if": condition, "go_to": if_state, "else_go_to": else_state if else_actions else next_state}
        ]

        self.state(name, check_actions, transitions)
        self.state(if_state, if_actions, on_success=next_state)

        if else_actions:
            self.state(else_state, else_actions, on_success=next_state)

        if not self.doc["start"]:
            self.start(name)

        return self

    def error_recovery(self, name: str, recovery_actions: List[Dict[str, Any]],
                       retry_state: str, max_retries: int = 3) -> 'WorkflowBuilder':
        """添加错误恢复机制"""
        retry_counter = f"{name}_retry_count"

        # 设置重试计数器
        self.set_var(retry_counter, 0)

        # 恢复动作 + 递增重试计数
        recovery_with_count = recovery_actions + [
            {"do": "increment_variable", "name": retry_counter}
        ]

        # 重试条件
        transitions = [
            {"if": f"@{retry_counter} < {max_retries}", "go_to": retry_state, "else_go_to": "error_final"}
        ]

        self.state(name, recovery_with_count, transitions)

        # 最终错误状态
        self.state("error_final", [
            {"do": "instr.answer_user", "text": f"Maximum retries ({max_retries}) exceeded"}
        ])

        return self

    def add_step(self, state_name: str, action: Dict[str, Any]) -> 'WorkflowBuilder':
        """向现有状态添加步骤"""
        if state_name in self.doc["states"]:
            self.doc["states"][state_name]["actions"].append(action)
        return self

    def build(self) -> Dict[str, Any]:
        """构建并返回工作流JSON"""
        # 验证必要字段
        if not self.doc["start"]:
            raise ValueError("Workflow must have a start state")

        if not self.doc["states"]:
            raise ValueError("Workflow must have at least one state")

        if self.doc["start"] not in self.doc["states"]:
            raise ValueError(f"Start state '{self.doc['start']}' not found in states")

        return copy.deepcopy(self.doc)

    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.build(), indent=indent, ensure_ascii=False)

    def save_to_file(self, filename: str) -> None:
        """保存到文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

# 快捷创建函数
def workflow(name: str = None, version: str = "1.3") -> WorkflowBuilder:
    """创建新的工作流构建器"""
    return WorkflowBuilder(version, name)

# 预设模板
class WorkflowTemplates:
    """工作流模板"""

    @staticmethod
    def indeed_apply_loop(count: int = 10) -> WorkflowBuilder:
        """Indeed循环申请模板"""
        return (workflow("indeed_apply_loop")
                .description("循环申请Indeed职位")
                .for_range(
                    name="apply",
                    counter="i",
                    count_expr=count,
                    body_actions=[
                        {"do": "task.run", "name": "indeed.apply_current",
                         "args": {"i": "@i"}, "save": "apply_result"}
                    ]
                )
                .state("done", [
                    {"do": "instr.answer_user", "text": f"申请完成，共申请了{count}个职位"}
                ]))

    @staticmethod
    def wechat_poll_reply(period_ms: int = 5000) -> WorkflowBuilder:
        """微信轮询回复模板"""
        return (workflow("wechat_poll_reply")
                .description("微信轮询新消息并回复")
                .poll(
                    name="poll_messages",
                    period_ms=period_ms,
                    actions=[
                        {"do": "anchor.find", "template": "wx_red_dot",
                         "region": "@wx_sidebar_bbox", "save": "red_dot"},
                        {"do": "instr.click", "target": {"bbox_var": "@red_dot"}},
                        {"do": "instr.read", "target": {"bbox_var": "@chat_view_bbox"},
                         "fields": ["lines"], "save": "messages"},
                        {"do": "task.run", "name": "wechat.send_message",
                         "args": {"user_anchor": "@contact_anchor", "text": "收到"}}
                    ]
                ))

    @staticmethod
    def web_login_sequence(site_name: str = "website") -> WorkflowBuilder:
        """通用网页登录序列模板"""
        return (workflow(f"{site_name}_login")
                .description(f"{site_name}登录流程")
                .set_vars({"username": "test_user", "password": "test_pass"})
                .task_sequence(
                    name="login_flow",
                    tasks=[
                        {"name": "web.generic_login",
                         "args": {"username": "@username", "password": "@password"}},
                        {"name": "web.verify_login", "save": "login_status"}
                    ]
                ))

    @staticmethod
    def data_extraction_pipeline(source: str, extractors: List[str]) -> WorkflowBuilder:
        """数据提取管道模板"""
        extract_tasks = []
        for i, extractor in enumerate(extractors):
            extract_tasks.append({
                "name": f"extract.{extractor}",
                "args": {"source": source if i == 0 else f"@step_{i-1}_result"},
                "save": f"step_{i}_result"
            })

        return (workflow("data_extraction_pipeline")
                .description(f"从{source}提取数据")
                .task_sequence("extraction", extract_tasks))

# 使用示例
if __name__ == "__main__":
    # 示例：创建Indeed申请工作流
    wf = (workflow("indeed_demo")
          .description("Indeed求职申请演示")
          .set_vars({"max_applications": 5})
          .autofix("auto_promote_on_success",
                   promote={"enabled": True, "threshold": {"successes": 10}})
          .for_range("apply", "i", "@max_applications", [
              {"do": "instr.scroll", "target": {"css": "div.left-pane"},
               "dir": "down", "amount": 600},
              {"do": "instr.click", "target": {"css": "div.left-pane .job-card:nth-child(@i+1)"}},
              {"do": "instr.wait", "ms": 500},
              {"do": "instr.click", "target": {"role": "button", "text": "Apply"}}
          ])
          .state("done", [
              {"do": "instr.answer_user", "text": "申请完成，共申请了@max_applications个职位"}
          ]))

    print(wf.to_json())