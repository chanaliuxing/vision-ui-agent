import logging, sys
from . import ENGINE_VERSION

def setup_logger():
    logger = logging.getLogger("auto")
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        fmt="%(asctime)s | v=%(engine)s | lvl=%(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    h.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(h)
    # 统一 extra
    class VersionAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            extra = kwargs.setdefault("extra", {})
            extra.setdefault("engine", ENGINE_VERSION)
            return msg, kwargs
    return VersionAdapter(logger, {})