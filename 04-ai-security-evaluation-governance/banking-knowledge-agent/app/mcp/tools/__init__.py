"""The six synthetic banking support tools.

One module per tool, and that is the whole design. Each module owns its tool's
implementation *and* its tool's synthetic dataset, and imports nothing from its
siblings.

**Why no shared fixture module.** A single ``data.py`` holding every component,
error code and transaction would have removed some duplication -- the nine
component names appear in five of these modules -- and it would also have made
the six tools a single unit of work with a single author. Keeping the data local
is what made them six genuinely independent files, which is what allowed them to
be built in parallel by six sub-agents against a frozen contract.

The duplication is real and it is not free. It cost exactly one bug, caught at
integration: ``check_service_health`` reported the platform line ``4.2`` as every
service's running version, while ``retrieve_system_version`` -- written in
parallel, from the same corpus -- knew that two components had not reached the
current build. Two tools contradicting each other about the same fact is worse
than either being absent. The fix keeps the datasets separate and adds a
cross-tool test asserting they agree, because the alternative -- a shared
constants module -- would give up the independence that made the parallel build
possible, in order to prevent a class of bug a test detects reliably.

That trade, and the rest of the integration friction, is recorded in
``docs/HANDOVER.md`` section 6.C and explained at length in
``docs/architecture-guide.html`` section 21.

Tools are registered explicitly in :mod:`app.mcp.factory`. Nothing in this
package self-registers on import.
"""

from app.mcp.tools.component_status import ComponentStatusTool
from app.mcp.tools.error_code import ErrorCodeLookupTool
from app.mcp.tools.service_health import ServiceHealthTool
from app.mcp.tools.system_configuration import SystemConfigurationTool
from app.mcp.tools.system_version import SystemVersionTool
from app.mcp.tools.transaction_status import TransactionStatusTool

__all__ = [
    "ComponentStatusTool",
    "ErrorCodeLookupTool",
    "ServiceHealthTool",
    "SystemConfigurationTool",
    "SystemVersionTool",
    "TransactionStatusTool",
]
