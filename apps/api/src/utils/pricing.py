"""Pricing tier configuration for billing system"""

from typing import Any, Dict, Union

PRICING_TIERS: Dict[str, Dict[str, Any]] = {
	"free": {
		"name": "Free",
		"price_monthly": 0,
		"features": {
			"episodes_per_month": 5,
			"storage_gb": 1,
			"api_calls_per_month": 3000,
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
			"api_calls_per_month": 300000,
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
			"episodes_per_month": None,  # unlimited
			"storage_gb": None,  # unlimited
			"api_calls_per_month": None,  # unlimited
			"concurrent_generations": 50,
			"tts_providers": "all",
			"distribution_targets": None,  # unlimited
			"team_members": None,  # unlimited
		},
	},
}

OVERAGE_PRICING: Dict[str, float] = {
	"cost_per_episode_over_limit": 2.00,
	"cost_per_gb_per_month": 0.50,
}


def get_tier_features(tier: str) -> Dict[str, Any]:
	"""Return feature limits for a given tier."""
	tier_config = PRICING_TIERS.get(tier, PRICING_TIERS["free"])
	return tier_config["features"]


def get_tier_limit(tier: str, resource: str) -> Union[int, None]:
	"""Return the limit for a resource in a tier. None = unlimited."""
	features = get_tier_features(tier)
	return features.get(resource)


def is_unlimited(tier: str, resource: str) -> bool:
	"""Return True if the resource is unlimited for the tier."""
	return get_tier_limit(tier, resource) is None
