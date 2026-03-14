"""Pricing tier definitions and overage configuration for billing system"""

from typing import Any, Dict, Union

# Pricing tier definitions
PRICING_TIERS: Dict[str, Dict[str, Any]] = {
	"free": {
		"name": "Free",
		"price_monthly": 0,
		"features": {
			"episodes_per_month": 5,
			"storage_gb": 1,
			"api_calls_per_day": 100,
			"concurrent_generations": 1,
			"tts_providers": ["google"],
			"distribution_targets": 1,
			"team_members": 1,
		},
	},
	"pro": {
		"name": "Pro",
		"price_monthly": 29,
		"features": {
			"episodes_per_month": 100,
			"storage_gb": 50,
			"api_calls_per_day": 10000,
			"concurrent_generations": 5,
			"tts_providers": ["google", "openai", "elevenlabs"],
			"distribution_targets": 5,
			"team_members": 3,
		},
	},
	"enterprise": {
		"name": "Enterprise",
		"price_monthly": None,  # Custom pricing
		"features": {
			"episodes_per_month": "unlimited",
			"storage_gb": "unlimited",
			"api_calls_per_day": "unlimited",
			"concurrent_generations": 50,
			"tts_providers": "all",
			"distribution_targets": "unlimited",
			"team_members": "unlimited",
		},
	},
}

# Overage pricing
OVERAGE_PRICING: Dict[str, Union[float, int]] = {
	"cost_per_episode_over_limit": 2.00,
	"cost_per_gb_per_month": 0.50,
	"api_call_overage_threshold": 1_000_000,  # Free beyond this
}


def get_tier_features(tier: str) -> Dict[str, Any]:
	"""Get feature limits for a subscription tier.

	Args:
		tier: Subscription tier name (free, pro, enterprise)

	Returns:
		Dict of feature limits for the tier
	"""
	tier_config = PRICING_TIERS.get(tier, PRICING_TIERS["free"])
	return tier_config["features"]


def get_tier_price(tier: str) -> Union[float, None]:
	"""Get monthly price for a subscription tier.

	Args:
		tier: Subscription tier name

	Returns:
		Monthly price in USD, or None for custom pricing
	"""
	tier_config = PRICING_TIERS.get(tier, PRICING_TIERS["free"])
	return tier_config.get("price_monthly")


def is_unlimited(value: Union[int, str]) -> bool:
	"""Check if a feature limit is unlimited.

	Args:
		value: Feature limit value

	Returns:
		True if unlimited
	"""
	return value == "unlimited"
