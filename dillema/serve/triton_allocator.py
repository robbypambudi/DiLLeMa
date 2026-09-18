"""Give Triton a device allocator in every serving worker.

Kernels that build TMA tensor descriptors on the device (vLLM's FLA
`solve_tril`, used by the Qwen3.5 / Qwen3-Next gated-delta-net layers on
compute capability >= 9) need scratch memory from `triton.set_allocator`.
vLLM 0.18 installs one only for a few models, and Triton keeps it in a
ContextVar, so even a process-wide `set_allocator` call does not reach the
thread Ray's compiled DAG runs the model in. The first request then fails with
"Kernel requires a runtime memory allocation, but no allocator was set" and
the engine dies.

Replacing the behaviour of Triton's default (null) allocator makes the
fallback itself allocate, in every thread, which is what vLLM's own
`set_triton_allocator` would have provided.
"""


def install() -> None:
    """Ray `worker_process_setup_hook`: runs once in each worker process."""
    try:
        import torch
        from triton.runtime import _allocation
    except ImportError:  # a CPU-only worker, or a Triton without allocators
        return

    def allocate(self, size: int, alignment: int, stream: int | None):
        # The caching allocator's blocks are 512-byte aligned, which covers
        # the alignment Triton asks for.
        return torch.empty(size, device="cuda", dtype=torch.int8)

    _allocation.NullAllocator.__call__ = allocate
