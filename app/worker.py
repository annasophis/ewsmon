# app/worker.py
from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Tuple, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
import requests
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.logger import configure_root_logging, get_logger
from app.models import ApiTarget, ApiProbe, WebhookSubscription
from app import notifications
import app.settings as settings

log = get_logger(__name__)


def _today_yyyy_mm_dd_utc() -> str:
    # timezone-aware UTC (no deprecation warning)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_et_iso() -> str:
    """Current time in America/Toronto (ET) for alert cards."""
    return datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %I:%M:%S %p ET")


def _is_uat_target(target: ApiTarget) -> bool:
    """
    Detect cert/UAT targets based on the host.
    (Seed uses certwebservices.purolator.com)
    """
    return "://certwebservices.purolator.com" in (target.url or "")


def _env_auth_and_account(target: ApiTarget) -> tuple[str, str, str]:
    """
    Returns (key, password, account) for the target environment.
    """
    if _is_uat_target(target):
        return (
            getattr(settings, "PUROLATOR_UAT_KEY", "") or "",
            getattr(settings, "PUROLATOR_UAT_PASSWORD", "") or "",
            getattr(settings, "PUROLATOR_UAT_ACCOUNT", "") or "",
        )
    return (
        getattr(settings, "PUROLATOR_KEY", "") or "",
        getattr(settings, "PUROLATOR_PASSWORD", "") or "",
        getattr(settings, "PUROLATOR_ACCOUNT", "") or "",
    )


def _env_label(target: ApiTarget) -> str:
    return "UAT" if _is_uat_target(target) else "PROD"


def build_payload(target: ApiTarget, acct: str) -> Tuple[Optional[str], Dict[str, str]]:
    """
    Returns: (soap_xml_string or None, headers_dict)

    If soap_xml is None, caller should treat it as a failed probe
    and store an error message (instead of crashing the worker).
    """
    headers: Dict[str, str] = {
        "Content-Type": "text/xml;charset=UTF-8",
    }

    # SOAPAction is critical for Purolator EWS (when required by the service)
    if target.soap_action:
        headers["SOAPAction"] = target.soap_action

    today = _today_yyyy_mm_dd_utc()
    purolator_date = f"<v1:Date>{today}</v1:Date>"

    if target.api_type == "validate":
        soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://purolator.com/pws/datatypes/v2">
  <soapenv:Header>
    <v2:RequestContext>
      <v2:Version>2.0</v2:Version>
      <v2:Language>en</v2:Language>
      <v2:GroupID>123</v2:GroupID>
      <v2:RequestReference>UserRef</v2:RequestReference>
    </v2:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v2:ValidateShipmentRequest>
      <v2:Shipment>
        <v2:SenderInformation>
          <v2:Address>
            <v2:Name>Test Name</v2:Name>
            <v2:Company>Test Company</v2:Company>
            <v2:Department>Test Department</v2:Department>
            <v2:StreetNumber>123</v2:StreetNumber>
            <v2:StreetSuffix/>
            <v2:StreetName>Edenwood</v2:StreetName>
            <v2:StreetType>Drive</v2:StreetType>
            <v2:StreetDirection/>
            <v2:Suite>123</v2:Suite>
            <v2:Floor>456</v2:Floor>
            <v2:StreetAddress2/>
            <v2:StreetAddress3/>
            <v2:City>boucherville</v2:City>
            <v2:Province>qc</v2:Province>
            <v2:Country>CA</v2:Country>
            <v2:PostalCode>j4b6h5</v2:PostalCode>
            <v2:PhoneNumber>
              <v2:CountryCode>1</v2:CountryCode>
              <v2:AreaCode>905</v2:AreaCode>
              <v2:Phone>7859425</v2:Phone>
              <v2:Extension></v2:Extension>
            </v2:PhoneNumber>
            <v2:FaxNumber>
              <v2:CountryCode/>
              <v2:AreaCode/>
              <v2:Phone/>
              <v2:Extension/>
            </v2:FaxNumber>
          </v2:Address>
          <v2:TaxNumber>123456</v2:TaxNumber>
        </v2:SenderInformation>

        <v2:ReceiverInformation>
          <v2:Address>
            <v2:Name>Receiver Name</v2:Name>
            <v2:Company>Receiver Company</v2:Company>
            <v2:Department>Receiver Department</v2:Department>
            <v2:StreetNumber>123</v2:StreetNumber>
            <v2:StreetSuffix/>
            <v2:StreetName>Edenwood</v2:StreetName>
            <v2:StreetType>Drive</v2:StreetType>
            <v2:StreetDirection/>
            <v2:Suite>123</v2:Suite>
            <v2:Floor>456</v2:Floor>
            <v2:StreetAddress2/>
            <v2:StreetAddress3/>
            <v2:City>MISSISSAUGA</v2:City>
            <v2:Province>ON</v2:Province>
            <v2:Country>CA</v2:Country>
            <v2:PostalCode>L5N3B5</v2:PostalCode>
            <v2:PhoneNumber>
              <v2:CountryCode>1</v2:CountryCode>
              <v2:AreaCode>905</v2:AreaCode>
              <v2:Phone>7859425</v2:Phone>
              <v2:Extension>123</v2:Extension>
            </v2:PhoneNumber>
            <v2:FaxNumber>
              <v2:CountryCode/>
              <v2:AreaCode/>
              <v2:Phone/>
              <v2:Extension/>
            </v2:FaxNumber>
          </v2:Address>
          <v2:TaxNumber>123456</v2:TaxNumber>
        </v2:ReceiverInformation>

        <v2:PackageInformation>
          <v2:ServiceID>PurolatorExpressEnvelope9AM</v2:ServiceID>
          <v2:Description>My Description</v2:Description>
          <v2:TotalWeight>
            <v2:Value>1</v2:Value>
            <v2:WeightUnit>lb</v2:WeightUnit>
          </v2:TotalWeight>
          <v2:TotalPieces>1</v2:TotalPieces>
          <v2:DangerousGoodsDeclarationDocumentIndicator>false</v2:DangerousGoodsDeclarationDocumentIndicator>
          <v2:OptionsInformation>
            <v2:Options>
              <v2:OptionIDValuePair>
                <v2:ID>ResidentialSignatureDomestic</v2:ID>
                <v2:Value>true</v2:Value>
              </v2:OptionIDValuePair>
            </v2:Options>
          </v2:OptionsInformation>
        </v2:PackageInformation>

        <v2:PaymentInformation>
          <v2:PaymentType>Sender</v2:PaymentType>
          <v2:RegisteredAccountNumber>{acct}</v2:RegisteredAccountNumber>
          <v2:BillingAccountNumber>{acct}</v2:BillingAccountNumber>
        </v2:PaymentInformation>

        <v2:PickupInformation>
          <v2:PickupType>DropOff</v2:PickupType>
        </v2:PickupInformation>

        <v2:NotificationInformation>
          <v2:ConfirmationEmailAddress></v2:ConfirmationEmailAddress>
        </v2:NotificationInformation>

        <v2:TrackingReferenceInformation>
          <v2:Reference1>REF1</v2:Reference1>
          <v2:Reference2>REF2</v2:Reference2>
          <v2:Reference3>REF3</v2:Reference3>
        </v2:TrackingReferenceInformation>

        <v2:OtherInformation>
          <v2:CostCentre>Cost Center</v2:CostCentre>
          <v2:SpecialInstructions>Special Instructions</v2:SpecialInstructions>
        </v2:OtherInformation>

        <v2:ProactiveNotification>
          <v2:RequestorName>RequestorName</v2:RequestorName>
          <v2:RequestorEmail>Requestor@Email.com</v2:RequestorEmail>
          <v2:Subscriptions>
            <v2:Subscription>
              <v2:Name>Name</v2:Name>
              <v2:Email>Test@Email.com</v2:Email>
              <v2:NotifyWhenExceptionOccurs>true</v2:NotifyWhenExceptionOccurs>
              <v2:NotifyWhenDeliveryOccurs>true</v2:NotifyWhenDeliveryOccurs>
            </v2:Subscription>
          </v2:Subscriptions>
        </v2:ProactiveNotification>

      </v2:Shipment>
    </v2:ValidateShipmentRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "track":
        # allow env-specific test PINs
        pin = (
            getattr(settings, "PUROLATOR_TRACK_PIN_UAT", None)
            if _is_uat_target(target)
            else getattr(settings, "PUROLATOR_TRACK_PIN", None)
        )
        pin = pin or "335258857374"

        soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v1="http://purolator.com/pws/datatypes/v1">
  <soapenv:Header>
    <v1:RequestContext>
      <v1:Version>1.2</v1:Version>
      <v1:Language>en</v1:Language>
      <v1:GroupID>monitor</v1:GroupID>
      <v1:RequestReference>monitor</v1:RequestReference>
    </v1:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v1:TrackPackagesByPinRequest>
      <v1:PINs>
        <v1:PIN><v1:Value>{pin}</v1:Value></v1:PIN>
      </v1:PINs>
    </v1:TrackPackagesByPinRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "freighttrack":
        # allow env-specific test PINs
        pin = (
            getattr(settings, "PUROLATOR_FREIGHT_TRACK_PIN_UAT", None)
            if _is_uat_target(target)
            else getattr(settings, "PUROLATOR_FREIGHT_TRACK_PIN", None)
        )
        pin = pin or "8889768050"

        soap_request = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v1="http://purolator.com/pws/datatypes/v1">
   <soapenv:Header>
      <v1:RequestContext>
         <!--type: string-->
         <v1:Version>1.0</v1:Version>
         <!--type: Language - enumeration: [en,fr]-->
         <v1:Language>en</v1:Language>
         <!--type: string-->
         <v1:GroupID></v1:GroupID>
         <!--type: string-->
         <v1:RequestReference>Freight Tracking</v1:RequestReference>
         <!--Optional:-->
         <!--type: string-->
         <v1:UserToken></v1:UserToken>
      </v1:RequestContext>
   </soapenv:Header>
   <soapenv:Body>
      <v1:TrackPackageByPINSearchCriteria>
         <v1:PINs>
            <!--Zero or more repetitions:-->
            <v1:PIN>
               <!--type: string-->
               <v1:Value>{pin}</v1:Value>
            </v1:PIN>
         </v1:PINs>
         <!--Optional:-->
         <!--type: string-->
         <v1:SearchType></v1:SearchType>
      </v1:TrackPackageByPINSearchCriteria>
   </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "freightestimate":
        # allow env-specific test PINs
          acct = (
            getattr(settings, "PUROLATOR_UAT_FREIGHT_ACCOUNT", None)
            if _is_uat_target(target)
            else getattr(settings, "PUROLATOR_FREIGHT_ACCOUNT", None)
        )
          acct = acct or "5553761"

          soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns="http://purolator.com/pws/datatypes/v1">
    <soapenv:Header>
        <RequestContext>
            <!--type: string-->
            <Version>1.1</Version>
            <!--type: Language - enumeration: [en,fr]-->
            <Language>en</Language>
            <!--type: string-->
            <GroupID></GroupID>
            <!--type: string-->
            <RequestReference>FREIGHT SHIPMENT</RequestReference>
        </RequestContext>
    </soapenv:Header>
    <soapenv:Body>
        <FreightGetEstimateRequest>
            <Estimate>
                <SenderInformation>
                    <Address>
                        <!--type: string-->
                        <Name>Ernest Sweetland</Name>
                        <!--Optional:-->
                        <!--type: string-->
                        <Company>Purolator Inc</Company>
                        <!--Optional:-->
                        <!--type: string-->
                        <Department>Shipping</Department>
                        <!--type: string-->
                        <StreetNumber>2727</StreetNumber>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetSuffix></StreetSuffix>
                        <!--type: string-->
                        <StreetName>Meadowpine</StreetName>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetType>Blvd</StreetType>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetDirection></StreetDirection>
                        <!--Optional:-->
                        <!--type: string-->
                        <Suite></Suite>
                        <!--Optional:-->
                        <!--type: string-->
                        <Floor></Floor>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetAddress2></StreetAddress2>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetAddress3></StreetAddress3>
                        <!--type: string-->
                        <City>Mississauga</City>
                        <!--type: string-->
                        <Province>ON</Province>
                        <!--type: string-->
                        <Country>CA</Country>
                        <!--type: string-->
                        <PostalCode>L5N 0E1</PostalCode>
                        <PhoneNumber>
                            <!--type: string-->
                            <CountryCode>1</CountryCode>
                            <!--type: string-->
                            <AreaCode>123</AreaCode>
                            <!--type: string-->
                            <Phone>1234567</Phone>
                            <!--Optional:-->
                            <!--type: string-->
                            <Extension>1234</Extension>
                        </PhoneNumber>
                        <!--Optional:-->
                        <FaxNumber>
                            <!--type: string-->
                            <CountryCode>1</CountryCode>
                            <!--type: string-->
                            <AreaCode>123</AreaCode>
                            <!--type: string-->
                            <Phone>1234567</Phone>
                            <!--Optional:-->
                            <!--type: string-->
                            <Extension>1234</Extension>
                        </FaxNumber>
                    </Address>
                    <!--Optional:-->
                    <!--type: string-->
                    <EmailAddress></EmailAddress>
                </SenderInformation>
                <ReceiverInformation>
                    <Address>
                        <!--type: string-->
                        <Name>George H. Greenhalgh</Name>
                        <!--Optional:-->
                        <!--type: string-->
                        <Company>Trans-Canada Couriers Ltd</Company>
                        <!--Optional:-->
                        <!--type: string-->
                        <Department>Warehousing</Department>
                        <!--type: string-->
                        <StreetNumber>3146</StreetNumber>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetSuffix></StreetSuffix>
                        <!--type: string-->
                        <StreetName>Bassel Street</StreetName>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetType>Street</StreetType>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetDirection></StreetDirection>
                        <!--Optional:-->
                        <!--type: string-->
                        <Suite></Suite>
                        <!--Optional:-->
                        <!--type: string-->
                        <Floor></Floor>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetAddress2></StreetAddress2>
                        <!--Optional:-->
                        <!--type: string-->
                        <StreetAddress3></StreetAddress3>
                        <!--type: string-->
                        <City>Pitt Meadows</City>
                        <!--type: string-->
                        <Province>BC</Province>
                        <!--type: string-->
                        <Country>CA</Country>
                        <!--type: string-->
                        <PostalCode>V3Y 2J4</PostalCode>
                        <PhoneNumber>
                            <!--type: string-->
                            <CountryCode>1</CountryCode>
                            <!--type: string-->
                            <AreaCode>123</AreaCode>
                            <!--type: string-->
                            <Phone>1234567</Phone>
                            <!--Optional:-->
                            <!--type: string-->
                            <Extension>1234</Extension>
                        </PhoneNumber>
                        <!--Optional:-->
                        <FaxNumber>
                            <!--type: string-->
                            <CountryCode>1</CountryCode>
                            <!--type: string-->
                            <AreaCode>123</AreaCode>
                            <!--type: string-->
                            <Phone>1234567</Phone>
                            <!--Optional:-->
                            <!--type: string-->
                            <Extension></Extension>
                        </FaxNumber>
                    </Address>
                    <!--Optional:-->
                    <!--type: string-->
                    <EmailAddress></EmailAddress>
                </ReceiverInformation>
                <PaymentInformation>
                    <!--type: PaymentType - enumeration: [Sender,Receiver,ThirdParty,CreditCard]-->
                    <PaymentType>Sender</PaymentType>
                    <!--type: string-->
                    <RegisteredAccountNumber>{acct}</RegisteredAccountNumber>
                    <!--Optional:-->
                    <!--type: string-->
                    <BillingAccountNumber>{acct}</BillingAccountNumber>
                </PaymentInformation>
                <ShipmentDetails>
                    <!--Optional:-->
                    <!--type: string -  I = Standard S= Expedited -->
                    <ServiceTypeCode>S</ServiceTypeCode>
                    <!--Optional:-->
                    <!--type: string-->
                    <ShipmentDate>2026-01-19</ShipmentDate>
                    <!--Optional:-->
                    <!--type: decimal-->
                    <DeclaredValue></DeclaredValue>
                    <!--Optional:-->
                    <!--type: decimal-->
                    <CODAmount></CODAmount>
                    <!--Optional:-->
                    <!--type: string-->
                    <SpecialInstructions>This is a test.</SpecialInstructions>
                    <LineItemDetails>
                        <LineItem>
                            <LineNumber>1</LineNumber>
                            <Pieces>1</Pieces>
                            <HandlingUnit>1</HandlingUnit>
                            <HandlingUnitType>Skid</HandlingUnitType>
                            <Description>MOTORCYCLE PARTS &amp; ACCESSORIES (MISC)</Description>
                            <Weight>
                                <Value>323</Value>
                                <WeightUnit>lb</WeightUnit>
                            </Weight>
                            <FreightClass>250</FreightClass>
                            <Length>
                                <Value>48.000</Value>
                                <DimensionUnit>in</DimensionUnit>
                            </Length>
                            <Width>
                                <Value>41.000</Value>
                                <DimensionUnit>in</DimensionUnit>
                            </Width>
                            <Height>
                                <Value>96.000</Value>
                                <DimensionUnit>in</DimensionUnit>
                            </Height>
                        </LineItem>
                        
                    </LineItemDetails>
                    <!--Optional:-->
                    <AccessorialParameters>
                        <!--Zero or more repetitions:-->
                        <BoolValuePair>
                            <!--type: string-->
                            <Keyword>2MEN</Keyword>
                            <!--type: boolean-->
                            <Value>false</Value>
                        </BoolValuePair>
                    </AccessorialParameters>
                </ShipmentDetails>
            </Estimate>
        </FreightGetEstimateRequest>
    </soapenv:Body>
</soapenv:Envelope>
"""
          return soap_request.strip(), headers

    if target.api_type == "locate":
        soap_request = """<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v1="http://purolator.com/pws/datatypes/v1">
  <soapenv:Header>
    <v1:RequestContext>
      <v1:Version>1.0</v1:Version>
      <v1:Language>en</v1:Language>
      <v1:GroupID>xx</v1:GroupID>
      <v1:RequestReference>xx</v1:RequestReference>
    </v1:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v1:GetLocationsByPostalCodeRequest>
      <v1:PostalCode>j4b6h5</v1:PostalCode>
      <v1:SearchOptions>
        <v1:RadialDistanceInKM>50</v1:RadialDistanceInKM>
      </v1:SearchOptions>
    </v1:GetLocationsByPostalCodeRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "estimate":
        soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://purolator.com/pws/datatypes/v2">
  <soapenv:Header>
    <v2:RequestContext>
      <v2:Version>2.0</v2:Version>
      <v2:Language>en</v2:Language>
      <v2:GroupID>1</v2:GroupID>
      <v2:RequestReference>UserRef</v2:RequestReference>
    </v2:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v2:GetQuickEstimateRequest>
      <v2:BillingAccountNumber>{acct}</v2:BillingAccountNumber>
      <v2:SenderPostalCode>J4B6H5</v2:SenderPostalCode>
      <v2:ReceiverAddress>
        <v2:City>Mississauga</v2:City>
        <v2:Province>ON</v2:Province>
        <v2:Country>CA</v2:Country>
        <v2:PostalCode>L4Y1K7</v2:PostalCode>
      </v2:ReceiverAddress>
      <v2:PackageType>ExpressBox</v2:PackageType>
      <v2:TotalWeight>
        <v2:Value>1</v2:Value>
        <v2:WeightUnit>lb</v2:WeightUnit>
      </v2:TotalWeight>
    </v2:GetQuickEstimateRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "pickup":
        soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v1="http://purolator.com/pws/datatypes/v1">
  <soapenv:Header>
    <v1:RequestContext>
      <v1:Version>1.0</v1:Version>
      <v1:Language>en</v1:Language>
      <v1:GroupID>123</v1:GroupID>
      <v1:RequestReference>UserRef</v1:RequestReference>
    </v1:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v1:ValidatePickUpRequest>
      <v1:BillingAccountNumber>{acct}</v1:BillingAccountNumber>
      <v1:PartnerID></v1:PartnerID>
      <v1:PickupInstruction>
        {purolator_date}
        <v1:AnyTimeAfter>1400</v1:AnyTimeAfter>
        <v1:UntilTime>1830</v1:UntilTime>
        <v1:TotalWeight><v1:Value>10</v1:Value><v1:WeightUnit>lb</v1:WeightUnit></v1:TotalWeight>
        <v1:TotalPieces>2</v1:TotalPieces>
        <v1:BoxesIndicator>true</v1:BoxesIndicator>
        <v1:PickUpLocation>BackDoor</v1:PickUpLocation>
        <v1:AdditionalInstructions></v1:AdditionalInstructions>
        <v1:SupplyRequestCodes><v1:SupplyRequestCode></v1:SupplyRequestCode></v1:SupplyRequestCodes>
        <v1:TrailerAccessible>false</v1:TrailerAccessible>
        <v1:LoadingDockAvailable>false</v1:LoadingDockAvailable>
        <v1:ShipmentOnSkids>false</v1:ShipmentOnSkids>
        <v1:NumberOfSkids>0</v1:NumberOfSkids>
      </v1:PickupInstruction>

      <v1:Address>
        <v1:Name>Test User</v1:Name>
        <v1:Company>User Test Company</v1:Company>
        <v1:Department>Test Dept</v1:Department>
        <v1:StreetNumber>5995</v1:StreetNumber>
        <v1:StreetSuffix></v1:StreetSuffix>
        <v1:StreetName>Avebury Road</v1:StreetName>
        <v1:StreetType>Road</v1:StreetType>
        <v1:StreetDirection></v1:StreetDirection>
        <v1:Suite></v1:Suite>
        <v1:Floor></v1:Floor>
        <v1:StreetAddress2></v1:StreetAddress2>
        <v1:StreetAddress3></v1:StreetAddress3>
        <v1:City>Boucherville</v1:City>
        <v1:Province>QC</v1:Province>
        <v1:Country>CA</v1:Country>
        <v1:PostalCode>J4B6H5</v1:PostalCode>
        <v1:PhoneNumber>
          <v1:CountryCode>1</v1:CountryCode>
          <v1:AreaCode>111</v1:AreaCode>
          <v1:Phone>1111111</v1:Phone>
          <v1:Extension>1111</v1:Extension>
        </v1:PhoneNumber>
        <v1:FaxNumber>
          <v1:CountryCode>1</v1:CountryCode>
          <v1:AreaCode>111</v1:AreaCode>
          <v1:Phone>1111111</v1:Phone>
          <v1:Extension>1111</v1:Extension>
        </v1:FaxNumber>
      </v1:Address>

      <v1:ShipmentSummary>
        <v1:ShipmentSummaryDetails>
          <v1:ShipmentSummaryDetail>
            <v1:DestinationCode>DOM</v1:DestinationCode>
            <v1:TotalPieces>2</v1:TotalPieces>
            <v1:TotalWeight><v1:Value>10</v1:Value><v1:WeightUnit>lb</v1:WeightUnit></v1:TotalWeight>
          </v1:ShipmentSummaryDetail>
        </v1:ShipmentSummaryDetails>
      </v1:ShipmentSummary>

      <v1:NotificationEmails>
        <v1:NotificationEmail>test.user@user.com</v1:NotificationEmail>
      </v1:NotificationEmails>
    </v1:ValidatePickUpRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "sa":
        soap_request = """<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://purolator.com/pws/datatypes/v2">
  <soapenv:Header>
    <v2:RequestContext>
      <v2:Version>2.0</v2:Version>
      <v2:Language>en</v2:Language>
      <v2:GroupID>11</v2:GroupID>
      <v2:RequestReference>UserRef</v2:RequestReference>
    </v2:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v2:ValidateCityPostalCodeZipRequest>
      <v2:Addresses>
        <v2:ShortAddress>
          <v2:City>Toronto</v2:City>
          <v2:Province>ON</v2:Province>
          <v2:Country>CA</v2:Country>
          <v2:PostalCode>L4Y1K7</v2:PostalCode>
        </v2:ShortAddress>
      </v2:Addresses>
    </v2:ValidateCityPostalCodeZipRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "shiptrack":
        tracking_id = (
            getattr(settings, "PUROLATOR_SHIPTRACK_ID_UAT", None)
            if _is_uat_target(target)
            else getattr(settings, "PUROLATOR_SHIPTRACK_ID", None)
        )
        tracking_id = tracking_id or "520111990344"

        # Prefer explicit v2 prefix to avoid namespace ambiguity
        soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://purolator.com/pws/datatypes/v2">
  <soapenv:Header>
    <v2:RequestContext>
      <v2:Version>2.0</v2:Version>
      <v2:Language>en</v2:Language>
      <v2:GroupID>Purolator</v2:GroupID>
      <v2:RequestReference>Shipment Tracking Service</v2:RequestReference>
    </v2:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v2:TrackingByPinsOrReferencesRequest>
      <v2:TrackingSearchCriteria>
        <v2:searches>
          <v2:search>
            <v2:trackingId>{tracking_id}</v2:trackingId>
            <v2:shipmentDateFrom>2025-01-01</v2:shipmentDateFrom>
            <v2:shipmentDateTo>2026-02-18</v2:shipmentDateTo>
            <v2:pod>false</v2:pod>
            <v2:shipmentView>true</v2:shipmentView>
            <v2:account>{acct}</v2:account>
          </v2:search>
        </v2:searches>
      </v2:TrackingSearchCriteria>
    </v2:TrackingByPinsOrReferencesRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    if target.api_type == "return":
        soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v2="http://purolator.com/pws/datatypes/v2">
  <soapenv:Header>
    <v2:RequestContext>
      <v2:Version>2.0</v2:Version>
      <v2:Language>en</v2:Language>
      <v2:GroupID>123</v2:GroupID>
      <v2:RequestReference>UserRef</v2:RequestReference>
    </v2:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <v2:ValidateReturnsManagementShipmentRequest>
      <v2:ReturnsManagementShipment>
        <v2:SenderInformation>
          <v2:Address>
            <v2:Name>Test Name</v2:Name>
            <v2:Company>Test Company</v2:Company>
            <v2:Department>Test Department</v2:Department>
            <v2:StreetNumber>123</v2:StreetNumber>
            <v2:StreetSuffix/>
            <v2:StreetName>Edenwood</v2:StreetName>
            <v2:StreetType>Drive</v2:StreetType>
            <v2:StreetDirection/>
            <v2:Suite>123</v2:Suite>
            <v2:Floor>456</v2:Floor>
            <v2:StreetAddress2/>
            <v2:StreetAddress3/>
            <v2:City>Toronto</v2:City>
            <v2:Province>ON</v2:Province>
            <v2:Country>CA</v2:Country>
            <v2:PostalCode>M6P3Y2</v2:PostalCode>
            <v2:PhoneNumber>
              <v2:CountryCode>1</v2:CountryCode>
              <v2:AreaCode>905</v2:AreaCode>
              <v2:Phone>7859425</v2:Phone>
              <v2:Extension></v2:Extension>
            </v2:PhoneNumber>
            <v2:FaxNumber>
              <v2:CountryCode/>
              <v2:AreaCode/>
              <v2:Phone/>
              <v2:Extension/>
            </v2:FaxNumber>
          </v2:Address>
          <v2:TaxNumber>123456</v2:TaxNumber>
        </v2:SenderInformation>

        <v2:ReceiverInformation>
          <v2:Address>
            <v2:Name>Receiver Name</v2:Name>
            <v2:Company>Receiver Company</v2:Company>
            <v2:Department>Receiver Department</v2:Department>
            <v2:StreetNumber>123</v2:StreetNumber>
            <v2:StreetSuffix/>
            <v2:StreetName>Edenwood</v2:StreetName>
            <v2:StreetType>Drive</v2:StreetType>
            <v2:StreetDirection/>
            <v2:Suite>123</v2:Suite>
            <v2:Floor>456</v2:Floor>
            <v2:StreetAddress2/>
            <v2:StreetAddress3/>
            <v2:City>MISSISSAUGA</v2:City>
            <v2:Province>ON</v2:Province>
            <v2:Country>CA</v2:Country>
            <v2:PostalCode>L5N3B5</v2:PostalCode>
            <v2:PhoneNumber>
              <v2:CountryCode>1</v2:CountryCode>
              <v2:AreaCode>905</v2:AreaCode>
              <v2:Phone>7859425</v2:Phone>
              <v2:Extension>123</v2:Extension>
            </v2:PhoneNumber>
            <v2:FaxNumber>
              <v2:CountryCode/>
              <v2:AreaCode/>
              <v2:Phone/>
              <v2:Extension/>
            </v2:FaxNumber>
          </v2:Address>
          <v2:TaxNumber>123456</v2:TaxNumber>
        </v2:ReceiverInformation>

        <v2:PackageInformation>
          <v2:ServiceID>PurolatorExpress</v2:ServiceID>
          <v2:Description>My Description</v2:Description>
          <v2:TotalWeight><v2:Value>1</v2:Value><v2:WeightUnit>lb</v2:WeightUnit></v2:TotalWeight>
          <v2:TotalPieces>1</v2:TotalPieces>
          <v2:PiecesInformation>
            <v2:Piece>
              <v2:Weight><v2:Value>1</v2:Value><v2:WeightUnit>lb</v2:WeightUnit></v2:Weight>
              <v2:Length><v2:Value>10</v2:Value><v2:DimensionUnit>in</v2:DimensionUnit></v2:Length>
              <v2:Width><v2:Value>10</v2:Value><v2:DimensionUnit>in</v2:DimensionUnit></v2:Width>
              <v2:Height><v2:Value>10</v2:Value><v2:DimensionUnit>in</v2:DimensionUnit></v2:Height>
            </v2:Piece>
          </v2:PiecesInformation>
          <v2:DangerousGoodsDeclarationDocumentIndicator>false</v2:DangerousGoodsDeclarationDocumentIndicator>
          <v2:OptionsInformation>
            <v2:Options>
              <v2:OptionIDValuePair>
                <v2:ID>ResidentialSignatureDomestic</v2:ID>
                <v2:Value>true</v2:Value>
              </v2:OptionIDValuePair>
            </v2:Options>
          </v2:OptionsInformation>
        </v2:PackageInformation>

        <v2:PaymentInformation>
          <v2:PaymentType>Sender</v2:PaymentType>
          <v2:RegisteredAccountNumber>{acct}</v2:RegisteredAccountNumber>
          <v2:BillingAccountNumber>{acct}</v2:BillingAccountNumber>
        </v2:PaymentInformation>

        <v2:PickupInformation><v2:PickupType>DropOff</v2:PickupType></v2:PickupInformation>

        <v2:NotificationInformation>
          <v2:ConfirmationEmailAddress></v2:ConfirmationEmailAddress>
        </v2:NotificationInformation>

        <v2:TrackingReferenceInformation>
          <v2:Reference1>REF1</v2:Reference1>
          <v2:Reference2>REF2</v2:Reference2>
          <v2:Reference3>REF3</v2:Reference3>
        </v2:TrackingReferenceInformation>

        <v2:OtherInformation>
          <v2:CostCentre>Cost Center</v2:CostCentre>
          <v2:SpecialInstructions>Special Instructions</v2:SpecialInstructions>
        </v2:OtherInformation>

        <v2:ProactiveNotification>
          <v2:RequestorName>RequestorName</v2:RequestorName>
          <v2:RequestorEmail>Requestor@Email.com</v2:RequestorEmail>
          <v2:Subscriptions>
            <v2:Subscription>
              <v2:Name>Name</v2:Name>
              <v2:Email>Test@Email.com</v2:Email>
              <v2:NotifyWhenExceptionOccurs>true</v2:NotifyWhenExceptionOccurs>
              <v2:NotifyWhenDeliveryOccurs>true</v2:NotifyWhenDeliveryOccurs>
            </v2:Subscription>
          </v2:Subscriptions>
        </v2:ProactiveNotification>

      </v2:ReturnsManagementShipment>
    </v2:ValidateReturnsManagementShipmentRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""
        return soap_request.strip(), headers

    # Unknown type: don't crash the worker
    return None, headers


async def probe_one(client: httpx.AsyncClient, target: ApiTarget) -> dict:
    key, pwd, acct = _env_auth_and_account(target)
    soap_xml, headers = build_payload(target, acct)

    if not soap_xml:
        return {
            "ok": False,
            "status": None,
            "ms": None,
            "error": f"payload not implemented for api_type={target.api_type}",
        }

    # Avoid noisy errors if env vars are missing
    if not key or not pwd:
        env = _env_label(target)
        return {"ok": False, "status": None, "ms": None, "error": f"missing creds for {env} (PUROLATOR_* env vars)"}

    start = time.perf_counter()
    try:
        resp = await client.post(
            target.url,
            content=soap_xml,
            headers=headers,
            auth=(key, pwd),
        )
        ms = (time.perf_counter() - start) * 1000.0

        ok = resp.status_code == 200
        if ok:
            return {"ok": True, "status": resp.status_code, "ms": ms, "error": None}

        # Capture some upstream info for debugging (stored in ApiProbe.error)
        ct = resp.headers.get("content-type", "")
        body_snip = (resp.text or "")[:800].replace("\n", "\\n")
        err = f"[{_env_label(target)}] http {resp.status_code} ct={ct} body_snip={body_snip}"

        return {"ok": False, "status": resp.status_code, "ms": ms, "error": err}

    except Exception as e:
        ms = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "status": None, "ms": ms, "error": f"[{_env_label(target)}] {type(e).__name__}: {e}"}


def persist_probes(db: Session, results: list[tuple[int, dict]]) -> int:
    """
    Insert probe rows for this cycle.
    Returns number inserted.
    """
    for target_id, probe in results:
        db.add(
            ApiProbe(
                target_id=target_id,
                ok=bool(probe.get("ok")),
                http_status=probe.get("status"),
                duration_ms=probe.get("ms"),
                error=probe.get("error"),
            )
        )
    db.commit()
    return len(results)


def cleanup_old_probes(db: Session, days: int) -> int:
    """
    Delete probes older than `days` days.
    Returns number deleted.
    """
    res = db.execute(
        text(
            """
            delete from api_probe
            where ts < (now() - (:days || ' days')::interval)
            """
        ),
        {"days": int(days)},
    )
    db.commit()
    return int(res.rowcount or 0)


def get_previous_probe_state(db: Session, target_ids: list[int]) -> dict[int, bool]:
    """
    For each target_id, return the ok state of the most recent probe before this cycle.
    Returns {target_id: ok}. Missing target_ids have no prior probe.
    """
    if not target_ids:
        return {}
    # PostgreSQL: DISTINCT ON (target_id) with ORDER BY target_id, ts DESC gives latest per target
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (target_id) target_id, ok
            FROM api_probe
            WHERE target_id = ANY(:target_ids)
            ORDER BY target_id, ts DESC
            """
        ),
        {"target_ids": target_ids},
    ).fetchall()
    return {int(r[0]): bool(r[1]) for r in rows}


WEBHOOK_REQUEST_TIMEOUT = 5


def fire_customer_webhooks(event_type: str, payload: dict) -> None:
    """
    POST payload to all active webhook subscriptions that subscribe to event_type.
    event_type is one of: up, down, incident, maintenance.
    Sends Content-Type: application/json and X-Webhook-Signature (HMAC-SHA256 of JSON body).
    Uses requests with 5s timeout; logs success/failure, does not raise.
    """
    with SessionLocal() as db:
        subs = db.query(WebhookSubscription).filter(WebhookSubscription.active == True).all()
        log.info("fire_customer_webhooks called", extra={"event_type": event_type, "subs_found": len(subs)})

    subscribed = [
        s for s in subs
        if event_type in [e.strip() for e in (s.events or "").split(",") if e.strip()]
    ]
    if not subscribed:
        return
    body = json.dumps(payload).encode("utf-8")
    for sub in subscribed:
        try:
            sig = hmac.new(
                sub.secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
            }
            r = requests.post(sub.url, data=body, headers=headers, timeout=WEBHOOK_REQUEST_TIMEOUT)
            if r.ok:
                log.info(
                    "webhook delivered",
                    extra={"webhook_id": sub.id, "event_type": event_type, "status_code": r.status_code},
                )
            else:
                log.warning(
                    "webhook delivery failed",
                    extra={"webhook_id": sub.id, "event_type": event_type, "status_code": r.status_code, "response": (r.text or "")[:200]},
                )
        except Exception as e:
            log.warning(
                "webhook delivery error",
                extra={"webhook_id": sub.id, "event_type": event_type, "error": str(e), "error_type": type(e).__name__},
            )


def _is_up(probe: dict) -> bool:
    """Current app: ok is True only for status 200. Treat that as UP."""
    return bool(probe.get("ok"))


async def main():
    configure_root_logging()
    init_db()

    # Support both names (your settings.py currently defines WORKER_INTERVAL_SECONDS)
    interval = int(getattr(settings, "POLL_INTERVAL_SECONDS", getattr(settings, "WORKER_INTERVAL_SECONDS", 10)))
    timeout_seconds = int(getattr(settings, "HTTP_TIMEOUT_SECONDS", 20))
    cleanup_every = int(getattr(settings, "CLEANUP_EVERY_SECONDS", 300))
    retention_days = int(getattr(settings, "PROBE_RETENTION_DAYS", 7))

    timeout = httpx.Timeout(timeout_seconds)
    last_cleanup = 0.0
    # Cooldown only for DOWN (avoid spam when flapping); RECOVERED is sent as soon as stable.
    _last_down_alert_ts: dict[int, float] = {}
    # RECOVERED only after 2 consecutive UP probes (stable); DOWN->UP sets pending, next UP sends.
    _pending_recovered: set[int] = set()

    log.info(
        "worker started",
        extra={"interval_seconds": interval, "timeout_seconds": timeout_seconds},
    )

    async with httpx.AsyncClient(http2=False, timeout=timeout) as client:
        while True:
            # Fetch targets using a short-lived session
            with SessionLocal() as db:
                targets = db.scalars(select(ApiTarget).where(ApiTarget.enabled == True)).all()

            if not targets:
                log.warning("no enabled targets")
            else:
                tasks = [probe_one(client, t) for t in targets]
                probes = await asyncio.gather(*tasks)
                results = list(zip([t.id for t in targets], probes))

                # Persist + cleanup + state-change alerts (same session for consistent prev state)
                target_ids = [t.id for t in targets]
                id_to_target = {t.id: t for t in targets}
                with SessionLocal() as db:
                    prev_state = get_previous_probe_state(db, target_ids)
                    inserted = persist_probes(db, results)

                    now = time.time()
                    if now - last_cleanup >= cleanup_every:
                        deleted = cleanup_old_probes(db, retention_days)
                        log.info(
                            "cleanup: deleted old probes",
                            extra={"deleted": deleted, "retention_days": retention_days},
                        )
                        last_cleanup = now

                    # State-change alerts: DOWN (with cooldown); RECOVERED only after 2 consecutive UPs (stable)
                    webhook_url = getattr(settings, "TEAMS_WEBHOOK_URL", "") or ""
                    cooldown_sec = int(getattr(settings, "ALERT_COOLDOWN_SECONDS", 300))
                    for target_id, probe in results:
                        current_up = _is_up(probe)
                        prev_up = prev_state.get(target_id)
                        if prev_up is None:
                            continue
                        target = id_to_target.get(target_id)
                        if not target or not webhook_url:
                            continue

                        # Same state as last time: only check if we can send RECOVERED (2nd consecutive UP)
                        if prev_up == current_up:
                            if current_up and target_id in _pending_recovered:
                                # Stable: two UPs in a row after a DOWN -> send RECOVERED
                                _pending_recovered.discard(target_id)
                                status_str = str(probe.get("status")) if probe.get("status") is not None else "timeout"
                                latency = probe.get("ms")
                                latency_str = f"{latency:.0f} ms" if latency is not None else "—"
                                time_str = _now_et_iso()
                                env = _env_label(target)
                                facts = {
                                    "Service": target.name,
                                    "Environment": env,
                                    "URL": target.url or "—",
                                    "HTTP Status": status_str,
                                    "Last Latency": latency_str,
                                    "Time": time_str,
                                }
                                await notifications.send_teams_card(
                                    f"{target.name} RECOVERED",
                                    "State change detected by EWS Monitoring (stable)",
                                    facts,
                                    webhook_url,
                                )
                                webhook_payload = {
                                    "event_type": "up",
                                    "service": target.name,
                                    "environment": env,
                                    "url": target.url or "",
                                    "http_status": status_str,
                                    "last_latency_ms": probe.get("ms"),
                                    "time": time_str,
                                }
                                await asyncio.to_thread(fire_customer_webhooks, "up", webhook_payload)
                                log.info(
                                    "alert sent",
                                    extra={
                                        "target_id": target_id,
                                        "prev_up": prev_up,
                                        "current_up": current_up,
                                        "status_code": probe.get("status"),
                                        "latency_ms": probe.get("ms"),
                                    },
                                )
                            continue

                        # State flip
                        if not prev_up and current_up:
                            # DOWN -> UP: wait for one more UP before sending RECOVERED (stable)
                            _pending_recovered.add(target_id)
                            continue
                        # UP -> DOWN: send DOWN (cooldown applies only here)
                        _pending_recovered.discard(target_id)
                        if (target_id in _last_down_alert_ts) and (
                            now - _last_down_alert_ts[target_id] < cooldown_sec
                        ):
                            continue
                        status_str = str(probe.get("status")) if probe.get("status") is not None else "timeout"
                        latency = probe.get("ms")
                        latency_str = f"{latency:.0f} ms" if latency is not None else "—"
                        time_str = _now_et_iso()
                        env = _env_label(target)
                        facts = {
                            "Service": target.name,
                            "Environment": env,
                            "URL": target.url or "—",
                            "HTTP Status": status_str,
                            "Last Latency": latency_str,
                            "Time": time_str,
                        }
                        await notifications.send_teams_card(
                            f"{target.name} DOWN",
                            "State change detected by EWS Monitoring",
                            facts,
                            webhook_url,
                        )
                        log.info("about to fire customer webhooks", extra={"target_id": target_id, "event_type": "down"})

                        webhook_payload = {
                            "event_type": "down",
                            "service": target.name,
                            "environment": env,
                            "url": target.url or "",
                            "http_status": status_str,
                            "last_latency_ms": probe.get("ms"),
                            "time": time_str,
                        }
                        await asyncio.to_thread(fire_customer_webhooks, "down", webhook_payload)
                        _last_down_alert_ts[target_id] = now
                        log.info(
                            "alert sent",
                            extra={
                                "target_id": target_id,
                                "prev_up": prev_up,
                                "current_up": current_up,
                                "status_code": probe.get("status"),
                                "latency_ms": probe.get("ms"),
                            },
                        )

                ok_count = sum(1 for _, r in results if r.get("ok"))
                log.info(
                    "probe cycle completed",
                    extra={"targets": inserted, "ok": ok_count},
                )

            await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())