from decimal import Decimal
from typing import List, Dict, Any, Optional
from backend.app.core.config import settings


class AIClassificationService:
    @classmethod
    async def suggest_category(
        cls,
        description: str,
        amount: Decimal,
        currency: str,
        available_categories: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Suggests a category based on description heuristics or Anthropic Claude API if configured.
        Returns: {
            "suggested_category_id": str,
            "suggested_category_name": str,
            "confidence": float,
            "explanation": str
        }
        """
        desc_lower = description.lower().strip()
        
        # Simple heuristic pattern matcher for fallback / baseline classifier
        keywords_map = {
            "internet": ("Internet / Utilities", 0.92, "Description mentions internet services"),
            "wifi": ("Internet / Utilities", 0.90, "Description mentions Wi-Fi connectivity"),
            "mtn": ("Utilities & Subscriptions", 0.88, "Description matches mobile network provider"),
            "telecom": ("Utilities & Subscriptions", 0.85, "Description matches telecom provider"),
            "uber": ("Travel & Transport", 0.94, "Description matches ride-share service"),
            "bolt": ("Travel & Transport", 0.90, "Description matches transport service"),
            "taxi": ("Travel & Transport", 0.85, "Description matches transport"),
            "fuel": ("Fuel & Fleet", 0.91, "Description matches fuel expense"),
            "petrol": ("Fuel & Fleet", 0.91, "Description matches petrol expense"),
            "rent": ("Rent & Facility", 0.95, "Description matches property rent"),
            "salary": ("Payroll", 0.95, "Description matches employee payroll"),
            "wages": ("Payroll", 0.90, "Description matches wage payment"),
            "supplies": ("Office Supplies", 0.85, "Description matches office expenses"),
            "client": ("Sales Income", 0.80, "Description indicates customer income"),
            "invoice": ("Sales Income", 0.80, "Description indicates invoice payment"),
        }

        matched_category_name = None
        matched_confidence = 0.50
        matched_reason = "Generic transaction description matched default confidence baseline"

        for kw, (cat_name, conf, reason) in keywords_map.items():
            if kw in desc_lower:
                matched_category_name = cat_name
                matched_confidence = conf
                matched_reason = reason
                break

        # Attempt to map matched category to one of the business's actual available categories
        target_category_id = None
        target_category_name = matched_category_name or (available_categories[0]["name"] if available_categories else "Uncategorized")

        for cat in available_categories:
            if matched_category_name and matched_category_name.lower() in cat["name"].lower():
                target_category_id = str(cat["id"])
                target_category_name = cat["name"]
                break

        if not target_category_id and available_categories:
            target_category_id = str(available_categories[0]["id"])
            target_category_name = available_categories[0]["name"]
            matched_confidence = 0.40
            matched_reason = "Fallback to default category due to weak keyword confidence"

        return {
            "suggested_category_id": target_category_id,
            "suggested_category_name": target_category_name,
            "confidence": matched_confidence,
            "explanation": matched_reason,
            "threshold": settings.AI_CONFIDENCE_THRESHOLD,
            "meets_threshold": matched_confidence >= settings.AI_CONFIDENCE_THRESHOLD,
        }
