"""
SOAP request builders for each Purolator API type.

Each builder returns (soap_xml: str, headers: dict) for use by the worker's
probe logic. Payload-specific logic (default PINs, account fallbacks, date
injection) lives in the respective builder.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import app.settings as settings

if TYPE_CHECKING:
    from app.models import ApiTarget


def _today_yyyy_mm_dd_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _is_uat_target(target: "ApiTarget") -> bool:
    """Duplicate of worker logic to avoid circular import. Cert/UAT uses certwebservices host."""
    return "://certwebservices.purolator.com" in (target.url or "")


def _base_headers(target: "ApiTarget") -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "text/xml;charset=UTF-8",
    }
    if target.soap_action:
        headers["SOAPAction"] = target.soap_action
    return headers


def build_validate_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    headers = _base_headers(target)
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


def build_track_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    pin = (
        getattr(settings, "PUROLATOR_TRACK_PIN_UAT", None)
        if _is_uat_target(target)
        else getattr(settings, "PUROLATOR_TRACK_PIN", None)
    )
    pin = pin or "335258857374"
    headers = _base_headers(target)
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


def build_freighttrack_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    pin = (
        getattr(settings, "PUROLATOR_FREIGHT_TRACK_PIN_UAT", None)
        if _is_uat_target(target)
        else getattr(settings, "PUROLATOR_FREIGHT_TRACK_PIN", None)
    )
    pin = pin or "8889768050"
    headers = _base_headers(target)
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


def build_freightestimate_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    freight_acct = (
        getattr(settings, "PUROLATOR_UAT_FREIGHT_ACCOUNT", None)
        if _is_uat_target(target)
        else getattr(settings, "PUROLATOR_FREIGHT_ACCOUNT", None)
    )
    freight_acct = freight_acct or "5553761"
    today = _today_yyyy_mm_dd_utc()
    headers = _base_headers(target)
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
                    <RegisteredAccountNumber>{freight_acct}</RegisteredAccountNumber>
                    <!--Optional:-->
                    <!--type: string-->
                    <BillingAccountNumber>{freight_acct}</BillingAccountNumber>
                </PaymentInformation>
                <ShipmentDetails>
                    <!--Optional:-->
                    <!--type: string -  I = Standard S= Expedited -->
                    <ServiceTypeCode>S</ServiceTypeCode>
                    <!--Optional:-->
                    <!--type: string-->
                    <ShipmentDate>{today}</ShipmentDate>
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


def build_locate_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    headers = _base_headers(target)
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


def build_estimate_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    headers = _base_headers(target)
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


def build_pickup_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    today = _today_yyyy_mm_dd_utc()
    purolator_date = f"<v1:Date>{today}</v1:Date>"
    headers = _base_headers(target)
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


def build_sa_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    headers = _base_headers(target)
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


def build_shiptrack_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    tracking_id = (
        getattr(settings, "PUROLATOR_SHIPTRACK_ID_UAT", None)
        if _is_uat_target(target)
        else getattr(settings, "PUROLATOR_SHIPTRACK_ID", None)
    )
    tracking_id = tracking_id or "520111990344"
    today = _today_yyyy_mm_dd_utc()
    headers = _base_headers(target)
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
            <v2:shipmentDateTo>{today}</v2:shipmentDateTo>
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


def build_return_payload(target: "ApiTarget", acct: str) -> tuple[str, dict[str, str]]:
    headers = _base_headers(target)
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
