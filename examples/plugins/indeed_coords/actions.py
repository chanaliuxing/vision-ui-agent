"""
Indeed坐标插件动作实现
重用Sprint A开发的坐标功能，作为插件形态演示
"""
from runtime.geom.coords import rect_center_to_screen_xy, get_os_monitors
from runtime.humanize.mouse import human_move_and_click, human_scroll


def click_coordinates(ctx, bbox, trace_tag=None, guard=None, **kwargs):
    """
    插件形态的坐标点击动作

    Args:
        ctx: 执行上下文
        bbox: 目标矩形
        trace_tag: 追踪标签
        guard: 安全防护配置
        **kwargs: 其他参数

    Returns:
        dict: 执行结果
    """
    try:
        # 安全校验
        if guard and guard.get("source_vars_only", False):
            # TODO: 实现来源校验逻辑
            pass

        # 获取页面度量信息
        page_metrics = getattr(ctx, 'page_metrics', {})
        if not page_metrics:
            page_metrics = {
                'dpr': 1.0,
                'screenX': 0,
                'screenY': 0,
                'outerHeight': 800,
                'innerHeight': 600,
                'monitor_id': 0
            }

        # 获取OS监视器信息
        os_monitors = get_os_monitors()

        # 坐标转换
        if isinstance(bbox, dict) and 'x' in bbox:
            screen_x, screen_y = rect_center_to_screen_xy(bbox, page_metrics, os_monitors)
        else:
            screen_x, screen_y = bbox

        # 记录事件
        if hasattr(ctx, 'events') and ctx.events:
            ctx.events.log("plugin.indeed_coords.click_coordinates", {
                "target_x": screen_x,
                "target_y": screen_y,
                "bbox": bbox,
                "trace_tag": trace_tag,
                "plugin": "indeed_coords v1.0.0"
            })

        # 检查人类化设置
        humanize_enabled = True
        if hasattr(ctx, 'features') and ctx.features:
            humanize_enabled = ctx.features.get('humanize', {}).get('mouse', True)

        # 执行点击
        human_move_and_click(screen_x, screen_y, humanize=humanize_enabled)

        return {
            "ok": True,
            "action": "click_coordinates",
            "plugin": "indeed_coords",
            "version": "1.0.0",
            "clicked_at": {"x": screen_x, "y": screen_y},
            "trace_tag": trace_tag
        }

    except Exception as e:
        # 记录错误
        if hasattr(ctx, 'events') and ctx.events:
            ctx.events.log("plugin.indeed_coords.click_coordinates.error", {
                "error": str(e),
                "bbox": bbox,
                "trace_tag": trace_tag,
                "plugin": "indeed_coords v1.0.0"
            })

        return {
            "ok": False,
            "action": "click_coordinates",
            "plugin": "indeed_coords",
            "version": "1.0.0",
            "error": str(e),
            "trace_tag": trace_tag
        }


def wheel_coordinates(ctx, at_bbox, amount, trace_tag=None, **kwargs):
    """
    插件形态的滚轮坐标动作

    Args:
        ctx: 执行上下文
        at_bbox: 容器矩形
        amount: 滚动量
        trace_tag: 追踪标签
        **kwargs: 其他参数

    Returns:
        dict: 执行结果
    """
    try:
        # 获取页面度量信息
        page_metrics = getattr(ctx, 'page_metrics', {})
        if not page_metrics:
            page_metrics = {
                'dpr': 1.0,
                'screenX': 0,
                'screenY': 0,
                'outerHeight': 800,
                'innerHeight': 600,
                'monitor_id': 0
            }

        # 获取OS监视器信息
        os_monitors = get_os_monitors()

        # 计算容器中心坐标
        if isinstance(at_bbox, dict) and 'x' in at_bbox:
            screen_x, screen_y = rect_center_to_screen_xy(at_bbox, page_metrics, os_monitors)
        else:
            screen_x, screen_y = at_bbox

        # 记录事件
        if hasattr(ctx, 'events') and ctx.events:
            ctx.events.log("plugin.indeed_coords.wheel_coordinates", {
                "target_x": screen_x,
                "target_y": screen_y,
                "amount": amount,
                "at_bbox": at_bbox,
                "trace_tag": trace_tag,
                "plugin": "indeed_coords v1.0.0"
            })

        # 执行滚动
        human_scroll(screen_x, screen_y, amount)

        return {
            "ok": True,
            "action": "wheel_coordinates",
            "plugin": "indeed_coords",
            "version": "1.0.0",
            "scrolled_at": {"x": screen_x, "y": screen_y},
            "amount": amount,
            "trace_tag": trace_tag
        }

    except Exception as e:
        # 记录错误
        if hasattr(ctx, 'events') and ctx.events:
            ctx.events.log("plugin.indeed_coords.wheel_coordinates.error", {
                "error": str(e),
                "at_bbox": at_bbox,
                "amount": amount,
                "trace_tag": trace_tag,
                "plugin": "indeed_coords v1.0.0"
            })

        return {
            "ok": False,
            "action": "wheel_coordinates",
            "plugin": "indeed_coords",
            "version": "1.0.0",
            "error": str(e),
            "trace_tag": trace_tag
        }