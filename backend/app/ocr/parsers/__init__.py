from . import aadhaar, driving_licence, pan

PARSERS = {"pan": pan.parse, "aadhaar": aadhaar.parse, "driving_licence": driving_licence.parse}
