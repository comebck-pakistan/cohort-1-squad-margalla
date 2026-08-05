"""Policy matching service — lookup store policies by type."""
from dataclasses import dataclass, field
from app.models.policy import StorePolicy


@dataclass
class PolicyMatchResult:
    """Result of a policy lookup."""
    matched: bool = False
    policy_type: str = ""
    policy_value: str = ""
    source: str = ""


class PolicyMatcher:
    """Match incoming requests to store policies."""

    # Map of requested_field → policy_type
    FIELD_TO_POLICY = {
        "cod": "cod",
        "delivery": "delivery",
        "delivery_charges": "delivery_charges",
        "returns": "returns",
        "exchange": "exchange",
        "delivery_locations": "delivery_locations",
        "store_info": "store_info",
    }

    def match(
        self,
        policies: list[StorePolicy],
        requested_fields: list[str],
    ) -> list[PolicyMatchResult]:
        """Match requested fields to store policies.

        Args:
            policies: Store's policies (already filtered to one store)
            requested_fields: Fields requested by the customer
        """
        results: list[PolicyMatchResult] = []

        policy_map = {p.policy_type: p for p in policies}

        for field_name in requested_fields:
            policy_type = self.FIELD_TO_POLICY.get(field_name)
            if policy_type and policy_type in policy_map:
                policy = policy_map[policy_type]
                results.append(PolicyMatchResult(
                    matched=True,
                    policy_type=policy_type,
                    policy_value=policy.policy_value,
                    source=f"policy:{policy_type}",
                ))

        return results

    def get_policy(self, policies: list[StorePolicy], policy_type: str) -> PolicyMatchResult:
        """Get a specific policy by type."""
        for policy in policies:
            if policy.policy_type == policy_type:
                return PolicyMatchResult(
                    matched=True,
                    policy_type=policy_type,
                    policy_value=policy.policy_value,
                    source=f"policy:{policy_type}",
                )
        return PolicyMatchResult(matched=False, policy_type=policy_type)
