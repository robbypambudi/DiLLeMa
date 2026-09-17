import torch
from loguru import logger


def embedding_device() -> str:
    """CUDA if the installed torch can actually run kernels; otherwise CPU.

    RTX 50-series (sm_120) reports cuda.is_available() with older torch builds
    but then fails encode() with "no kernel image is available".
    """
    if not torch.cuda.is_available():
        return "cpu"
    try:
        x = torch.zeros(1, device="cuda")
        _ = x + 1
        torch.cuda.synchronize()
        return "cuda"
    except RuntimeError as exc:
        logger.warning("CUDA unusable for embeddings ({}), using CPU", exc)
        return "cpu"
