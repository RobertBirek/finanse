from dataclasses import dataclass, field
from fnmatch import fnmatch


@dataclass
class PolicyEngine:
    HIGH_RISK_OPERATIONS: list[str] = field(default_factory=lambda: [
        "delete_*",
        "create_financial_*",
        "send_*",
    ])

    def check_autonomy(self, tool_name: str, requested_level: int) -> int:
        max_allowed = 4  # default max for read-only
        for pattern in self.HIGH_RISK_OPERATIONS:
            if fnmatch(tool_name, pattern):
                max_allowed = 2
                break
        return min(requested_level, max_allowed)


_policy_engine = PolicyEngine()


def get_policy_engine() -> PolicyEngine:
    return _policy_engine
