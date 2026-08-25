from config.settings import *


def create_buy_payload(
    price: float, 
    quantity: int, 
    security_id: int, 
    exchange_security_id: int):
    """
    - creates a new payload dict each time.
    No deepcopy from json payload needed.
    """
    return {
        "orderBook": {
            "orderBookExtensions": [{
                "orderTypes": {"id": 1, "orderTypeCode": "LMT"},
                "disclosedQuantity": 0,
                "orderValidity": {"id": 1, "orderValidityCode": "DAY"},
                "triggerPrice": 0,
                "orderPrice": price,  # ← Dynamic value
                "orderQuantity": quantity,  # ← Dynamic value
                "remainingOrderQuantity": quantity,  # ← Dynamic value
                "marketType": {"id": 2, "marketType": "Continuous"}
            }],
            "exchange": {"id": 1},
            "dnaConnection": {},
            "dealer": {},
            "member": {},
            "productType": {"id": 1, "productCode": "CNC"},
            "instrumentType": {"id": 1, "code": "EQ"},
            "client": {
                "activeStatus": "A",
                "id": ID,               # ← Dynamic value
                "accountType": "CLI",
                "allowedToTrade": "Y",
                "clientMemberCode": CLIENT_CODE,    # ← Dynamic value
                "clientOrDealer": "C",
                "contactNumber": PHONE_NUMBER,      # ← Dynamic value
                "emailId": None,
                "notsUniqueClientCode": NOT_UNIQUE_CLIENT_CODE,     # ← Dynamic value
                "clientDealerType": None,
                "clientGroup": {
                    "activeStatus": "A",
                    "id": 101,
                    "clientGroupCode": None,
                    "clientGroupName": None
                },
                "memberBranch": {
                    "activeStatus": "A",
                    "id": 2,
                    "branchLocation": None,
                    "branchName": None,
                    "hidden": None,
                    "branchProvince": None,
                    "branchDistrict": None,
                    "branchMunicipality": None,
                    "branchHead": None,
                    "branchPhoneNumber": None
                },
                "clientDealerAddressDetails": None,
                "clientDealerBankDetail": None,
                "clientDealerIndividual": None,
                "clientDealerPerTradeLimits": None,
                "clientDealerProductMappings": None,
                "clientDealerOrderTypeMappings": None,
                "clientDealerTradingLimits": None,
                "clientDepositoryDetail": None,
                "corporateDetail": None,
                "corporateOwnershipDetails": None,
                "displayName": NAME,
                "blockedDate": None,
                "remarks": None,
                "parentId": None,
                "recordType": None,
                "collateralByEntities": None,
                "shortSellMode": 0,
                "onlineOrOffline": 1,
                "panNumber": None,
                "onlineFundTransfer": None,
                "collateralCalculationMode": 1,
                "isMarginLendingClient": None,
                "clientRiskType": None,
                "userAgreementChecked": None,
                "referredBy": None,
                "responseStatus": None,
                "isCkycAccount": None,
                "kycUpload": False,
                "marginLendingClient": None
            },
            "security": {
                "id": security_id,  # ← Dynamic value
                "exchangeSecurityId": exchange_security_id,  # ← Dynamic value
                "marketProtectionPercentage": 0,
                "divisor": 100,
                "boardLotQuantity": 1,
                "tickSize": 0.1
            },
            "accountType": 1,
            "cpMemberId": 0,
            "buyOrSell": 1
        },
        "orderPlacedBy": 2,
        "exchangeOrderId": None
    }