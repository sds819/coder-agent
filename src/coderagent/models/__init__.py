"""Model backends and the gateway that fronts them."""

from functools import cache


@cache
def litellm_module():
    """litellm, imported on demand.

    Importing litellm takes about two seconds, and most commands never call a model.
    """
    import litellm

    litellm.suppress_debug_info = True
    """litellm prints banners to stdout, which would break the machine-readable output."""
    return litellm
