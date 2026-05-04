"""DEPRECATED: 此模块已废弃。

压缩职责由 StateExtractor + CompressionSummarizer 承担。
manager.py 直接调用新模块，不再经过 compressor.py。
保留此文件仅为向后兼容（如有外部引用）。
"""
import warnings

warnings.warn(
    "ContextCompressor is deprecated. Use StateExtractor + CompressionSummarizer instead.",
    DeprecationWarning,
    stacklevel=2,
)


class ContextCompressor:
    """DEPRECATED: 占位类，不再实现任何功能。"""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "ContextCompressor is deprecated. "
            "Use StateExtractor + CompressionSummarizer instead."
        )
