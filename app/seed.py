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

def seed_targets(db: Session) -> int:
    created = 0
    for t in DEFAULT_TARGETS:
        exists = db.query(ApiTarget).filter(ApiTarget.name == t["name"]).first()
        if exists:
            continue
        db.add(ApiTarget(**t))
        created += 1
    if created:
        db.commit()
    return created