from uuid import uuid4

import pytest

from tcp_lab.runtime import ROOT


@pytest.fixture
def run_dir(request):
    directory = ROOT / "build" / "test-runs" / f"{request.node.name}-{uuid4().hex[:12]}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory
