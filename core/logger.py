import logging


def _get_log_level(level_name: str = "INFO") -> int:
    """将日志级别名称转换为对应的整数值"""
    level_name = level_name.upper()
    level_map: dict[str, int] = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_name, logging.INFO)

def setup_logger(name: str | None = None, level: str = "INFO") -> logging.Logger:
    """To setup as many loggers as you want"""
    log_level = _get_log_level(level)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger = logging.getLogger(name or __name__)
    logger.setLevel(log_level)
    return logger
    