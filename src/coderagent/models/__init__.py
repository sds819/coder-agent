"""Model backends and the gateway that fronts them."""

import threading
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


def warm_up_litellm() -> None:
    """Import litellm in the background.

    A program that waits for the user has time to spare: the import happens while
    the user reads and types, and the first call does not wait for it.
    """

    def load() -> None:
        try:
            litellm_module()
        except Exception:
            """The call that needs litellm reports the failure; here it would only be noise."""

    threading.Thread(target=load, daemon=True).start()
