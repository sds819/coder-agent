"""litellm is loaded on demand: the coder does not wait for it."""

import subprocess
import sys


def test_the_warm_up_loads_litellm_in_the_background():
    """A program that waits for the user has time to spare."""
    code = (
        "import sys, time\n"
        "from coderagent.models import warm_up_litellm\n"
        "warm_up_litellm()\n"
        "deadline = time.time() + 60\n"
        "while time.time() < deadline and 'litellm' not in sys.modules:\n"
        "    time.sleep(0.05)\n"
        "print('litellm' in sys.modules)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "True"
