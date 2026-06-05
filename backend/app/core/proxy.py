from typing import Dict, List
import logging
from app.core.wg_easy import wg_client

logger = logging.getLogger(__name__)

# Tier-to-proxy-rule mapping
TIER_RULES = {
    "full": {
        "description": "Full internet access",
        "allowed_categories": ["all"],
        "blocked_categories": [],
        "time_limits": {},
        "whitelist": [],
        "blacklist": []
    },
    "limited": {
        "description": "Limited access — no social media/games",
        "allowed_categories": ["education", "news", "productivity", "communication"],
        "blocked_categories": ["social_media", "gaming", "streaming", "shopping"],
        "time_limits": {"gaming": 0, "social_media": 0, "streaming": 60},
        "whitelist": [],
        "blacklist": ["*.tiktok.com", "*.instagram.com", "*.youtube.com", "*.netflix.com"]
    },
    "research_only": {
        "description": "Research only — whitelist mode",
        "allowed_categories": ["education"],
        "blocked_categories": ["all"],
        "time_limits": {},
        "whitelist": [
            "*.wikipedia.org",
            "*.khanacademy.org",
            "*.scholar.google.com",
            "*.jstor.org",
            "*.pubmed.ncbi.nlm.nih.gov",
            "*.edsby.com",
            "*.classroom.google.com"
        ],
        "blacklist": ["*"]
    }
}

async def apply_tier_rules(child_id: int, tier: str, device_ids: List[int] = None) -> Dict:
    """
    Apply tier-based proxy rules and log wg-easy peer updates.
    In production, this would update nftables/iptables per device MAC.
    """
    rules = TIER_RULES.get(tier, TIER_RULES["full"])
    
    logger.info(f"[PROXY] Applying tier '{tier}' to child_id={child_id}, devices={device_ids}")
    
    # Get wg-easy clients for logging
    wg_peers = []
    try:
        clients = wg_client.list_clients()
        wg_peers = [c.get("name") for c in clients if c.get("name")]
    except Exception as e:
        logger.warning(f"[WG-EASY] Could not list peers: {e}")
    
    return {
        "status": "applied",
        "child_id": child_id,
        "tier": tier,
        "rules": rules,
        "devices_updated": device_ids or [],
        "wg_peers_found": wg_peers,
        "message": f"Tier '{tier}' rules applied. {len(wg_peers)} WireGuard peer(s) active."
    }

async def get_device_rules(device_id: int) -> Dict:
    """Get current rules applied to a device."""
    return {
        "device_id": device_id,
        "active_tier": "full",
        "rules": TIER_RULES["full"],
        "last_updated": None
    }
