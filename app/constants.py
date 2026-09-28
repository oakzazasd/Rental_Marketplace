"""Central application constants.

Everything that might need to be extended later lives here so it is easy to
find and change without touching business logic.
"""

ALLOWED_EMAIL_DOMAIN = "@kmitl.ac.th"

CATEGORIES = [
    "Electronics",
    "Computer",
    "Camera",
    "Photography",
    "Books",
    "Calculator",
    "Cables",
    "Projector",
    "Lab Equipment",
    "Tools",
    "Sports Equipment",
    "Other",
]

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------
ITEM_STATUSES = ("available", "unavailable", "deleted")
ITEM_STATUS_LABELS = {
    "available": "Available",
    "unavailable": "Unavailable",
    "deleted": "Deleted",
}

RENTAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "active",
    "completed",
    "cancelled",
)
RENTAL_STATUS_LABELS = {
    "pending": "Pending",
    "approved": "Approved",
    "rejected": "Rejected",
    "active": "Active",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
# Statuses that hold a date range on an item (blocking for availability).
RENTAL_BLOCKING_STATUSES = ("pending", "approved", "active", "completed")
# Statuses where the temporary chat room must exist.
RENTAL_CHAT_STATUSES = ("pending", "approved", "active")

TRANSACTION_STATUSES = ("pending", "authorized", "completed", "refunded")
TRANSACTION_STATUS_LABELS = {
    "pending": "Pending payment",
    "authorized": "Authorized",
    "completed": "Completed",
    "refunded": "Refunded",
}

AD_STATUSES = ("pending", "active", "expired", "cancelled")
AD_STATUS_LABELS = {
    "pending": "Pending",
    "active": "Active",
    "expired": "Expired",
    "cancelled": "Cancelled",
}

CHAT_ACTIVE = "active"
CHAT_CLOSED = "closed"
CHAT_STATUS_LABELS = {"active": "Active", "closed": "Closed"}

# ---------------------------------------------------------------------------
# Advertising
# ---------------------------------------------------------------------------
PROMOTION_LEVEL_BASIC = "Basic"
PROMOTION_LEVEL_STANDARD = "Standard"
PROMOTION_LEVEL_PREMIUM = "Premium"
PROMOTION_LEVEL_NAMES = (
    PROMOTION_LEVEL_BASIC,
    PROMOTION_LEVEL_STANDARD,
    PROMOTION_LEVEL_PREMIUM,
)
AD_DURATION_CHOICES = (1, 3, 7, 14, 30)
CURRENCY = "THB"
CURRENCY_SYMBOL = "฿"

# ---------------------------------------------------------------------------
# Image uploads
# ---------------------------------------------------------------------------
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_MAX_DIMENSION = 1280
IMAGE_JPEG_QUALITY = 85

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
DEFAULT_MAX_MESSAGE_LENGTH = 2000
