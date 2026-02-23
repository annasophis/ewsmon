from sqlalchemy.orm import Session
from app.models import ApiTarget

DEFAULT_TARGETS = [
    {
        "name": "Purolator Shipping Service",
        "url": "https://webservices.purolator.com/EWS/v2/Shipping/ShippingService.asmx",
        "soap_action": "http://purolator.com/pws/service/v2/ValidateShipment",
        "api_type": "validate",
    },
    {
        "name": "Purolator Package Tracking Service",
        "url": "https://webservices.purolator.com/EWS/V1/Tracking/TrackingService.asmx",
        "soap_action": "http://purolator.com/pws/service/v1/TrackPackagesByPin",
        "api_type": "track",
    },
    {
        "name": "Purolator Locator Service",
        "url": "https://webservices.purolator.com/EWS/V1/Locator/LocatorService.asmx",
        "soap_action": "http://purolator.com/pws/service/v1/GetLocationsByPostalCode",
        "api_type": "locate",
    },
    {
        "name": "Purolator Estimate Service",
        "url": "https://webservices.purolator.com/EWS/V2/Estimating/EstimatingService.asmx",
        "soap_action": "http://purolator.com/pws/service/v2/GetQuickEstimate",
        "api_type": "estimate",
    },
    {
        "name": "Purolator Pickup Service",
        "url": "https://webservices.purolator.com/EWS/V1/PickUp/PickUpService.asmx",
        "soap_action": "http://purolator.com/pws/service/v1/ValidatePickUp",
        "api_type": "pickup",
    },
    {
        "name": "Purolator Service Availability Service",
        "url": "https://webservices.purolator.com/EWS/V2/ServiceAvailability/ServiceAvailabilityService.asmx",
        "soap_action": "http://purolator.com/pws/service/v2/ValidateCityPostalCodeZip",
        "api_type": "sa",
    },
    {
        "name": "Purolator Returns Management Service",
        "url": "https://webservices.purolator.com/EWS/V2/ReturnsManagement/ReturnsManagementService.asmx",
        "soap_action": "http://purolator.com/pws/service/v2/ValidateReturnShipment",
        "api_type": "return",
    },
    {
        "name": "Purolator Shipment Tracking Service",
        "url": "https://webservices.purolator.com/EWS/V2/ShipmentTracking/ShipmentTrackingService.asmx",
        "soap_action": "http://purolator.com/pws/service/v2/TrackingByPinsOrReferences",
        "api_type": "shiptrack",
    },
]

def _to_uat_url(prod_url: str) -> str:
    # only swap the host; keep path/case exactly as-is
    return prod_url.replace(
        "https://webservices.purolator.com",
        "https://certwebservices.purolator.com",
    )

def seed_targets(db: Session) -> int:
    created = 0

    all_targets: list[dict] = []
    all_targets.extend(DEFAULT_TARGETS)

    # UAT targets (clone + rename + host swap)
    for t in DEFAULT_TARGETS:
        u = dict(t)
        u["name"] = f'{t["name"]} (UAT)'
        u["url"] = _to_uat_url(t["url"])
        all_targets.append(u)

    for t in all_targets:
        exists = db.query(ApiTarget).filter(ApiTarget.name == t["name"]).first()
        if exists:
            continue
        db.add(ApiTarget(**t))
        created += 1

    if created:
        db.commit()

    return created