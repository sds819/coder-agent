"""The environments the commands of the agent run in.

The local one runs the commands on the machine of the user. The other ones are
containers: Docker, Singularity, bubblewrap, contree, and the containers that
SWE-ReX and Modal manage. They are chosen with `sandbox.type` in the
configuration and they are imported only when they are used.
"""

from coderagent.environments.local import LocalEnvironment, LocalEnvironmentConfig, is_local

__all__ = ["LocalEnvironment", "LocalEnvironmentConfig", "is_local"]
