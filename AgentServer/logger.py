import logging
import sys

class TraceAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        trace_id = self.extra.get('trace_id', '-') if self.extra else '-'
        if 'extra' in kwargs and 'trace_id' in kwargs['extra']:
            trace_id = kwargs['extra']['trace_id']
        return f"[TraceID: {trace_id}] {msg}", kwargs

def setup_logger(name: str = "AgentServer") -> logging.Logger:
    """
    配置并返回企业级 Logger
    """
    logger = logging.getLogger(name)
    
    # 如果已经配置过 handler，直接返回避免重复
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] [%(module)s:%(lineno)d] - %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

logger = setup_logger()

def get_logger_with_trace(trace_id: str) -> logging.LoggerAdapter:
    """
    获取一个带 trace_id 的 logger adapter
    """
    return TraceAdapter(logger, {'trace_id': trace_id})
