import requests
import pandas as pd
import pickle

"""
Column names used from 1st databank:
---
NDC
Medication_Name (full name)
Strength
Form
Route
DEA_Class
Simple_Generic_1 (generic name)
Pharm_Class_1 (pharmacological class)
Thera_Class_1 (therapeutic class)
MME
"""

MME_TABLE = {}
MME_TABLE["butorphanol"] = 7
MME_TABLE["codeine"] = 0.15
MME_TABLE["dihydrocodeine"] = 0.25
MME_TABLE["hydrocodone"] = 4
MME_TABLE["hydromorphone"] = 5
MME_TABLE["levomethadyl acetate"] = 8
MME_TABLE["levorphanol tartrate"] = 11
MME_TABLE["meperidine"] = 0.1
MME_TABLE["methadone"] = 4.7
MME_TABLE["morphine"] = 1
MME_TABLE["opium"] = 1
MME_TABLE["oxycodone"] = 1.5
MME_TABLE["oxymorphone"] = 3
MME_TABLE["pentazocine"] = 0.37
MME_TABLE["tapentadol"] = 0.4
MME_TABLE["tramadol"] = 0.2


def get_rxcui_from_ndc(ndc):
    url = "https://rxnav.nlm.nih.gov/REST/ndcstatus.json"
    querystring = {"ndc": ndc}
    response = requests.request("GET", url, params=querystring)
    r = response.json()
    if r["ndcStatus"]["conceptStatus"] == "NOTCURRENT":
        return None
    if r["ndcStatus"]["status"] == "UNKNOWN":
        return None
    else:
        return r["ndcStatus"]["rxcui"]


def get_rxterms(rxcui, d):
    url = "https://rxnav.nlm.nih.gov/REST/RxTerms/rxcui/{}/allinfo.json".format(rxcui)
    response = requests.request("GET", url)
    r = response.json()
    if r.get("rxtermsProperties") == None:
        return
    d["Medication_Name"] = r["rxtermsProperties"]["fullName"]
    d["Simple_Generic_1"] = r["rxtermsProperties"]["fullGenericName"]
    d["Route"] = r["rxtermsProperties"]["route"]
    d["Form"] = r["rxtermsProperties"]["rxtermsDoseForm"]


def get_rxnorm_property(rxcui, propName):
    url = "https://rxnav.nlm.nih.gov/REST/rxcui/{}/property.json".format(rxcui)
    querystring = {"propName": propName}
    response = requests.request("GET", url, params=querystring)
    r = response.json()
    if r.get("propConceptGroup") is None:
        return None
    value = r["propConceptGroup"]["propConcept"][0]["propValue"]
    return value


def get_pharma_class(rxcui, d):
    url = "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json"
    querystring = {"rxcui": rxcui, "relaSource": "VA", "relas": "has_VAClass"}
    response = requests.request("GET", url, params=querystring)
    r = response.json()
    if "rxclassDrugInfoList" not in r:
        return None
    d["Pharm_Class_1"] = r["rxclassDrugInfoList"]["rxclassDrugInfo"][0][
        "rxclassMinConceptItem"
    ]["className"]
    class_id = r["rxclassDrugInfoList"]["rxclassDrugInfo"][0]["rxclassMinConceptItem"][
        "classId"
    ]
    return class_id


CLASS_CACHE = {}


def get_thera_class(classId, d):
    if classId not in CLASS_CACHE.keys():
        url = "https://rxnav.nlm.nih.gov/REST/rxclass/classGraph.json"
        querystring = {"classId": classId, "source": "VA"}
        response = requests.request("GET", url, params=querystring)
        resp = response.json()
        CLASS_CACHE[classId] = resp
    r = CLASS_CACHE[classId]
    d["Thera_Class_1"] = r["rxclassGraph"]["rxclassMinConceptItem"][1]["className"]


def calculate_MME(rxcui, d):
    url = "https://rxnav.nlm.nih.gov/REST/rxcui/{}/historystatus.json".format(rxcui)
    querystring = {"caller": "RxNav"}
    response = requests.request("GET", url, params=querystring)
    r = response.json()
    mme = 0
    for ingredient in (
        r.get("rxcuiStatusHistory", {})
        .get("definitionalFeatures", {})
        .get("ingredientAndStrength", [])
    ):
        baseName = ingredient["baseName"]
        value = ingredient["numeratorValue"]
        unit = ingredient["numeratorUnit"]
        if baseName.lower() == "buprenorphine":
            d["Strength_Per_Unit"] = float(value)
            if ingredient["denominatorUnit"] == "HR":
                d["MME_Conversion_Factor"] = 12600
            else:
                d["MME_Conversion_Factor"] = 30
            mme += d["MME_Conversion_Factor"] * d["Strength_Per_Unit"]
        elif baseName.lower() == "fentanyl":
            d["Strength_Per_Unit"] = float(value)
            doseForms = []
            try:
                doseForms = [
                    x["doseFormGroupName"]
                    for x in r["rxcuiStatusHistory"]["definitionalFeatures"][
                        "doseFormGroupConcept"
                    ]
                ]
            except:
                pass
            formConcepts = []
            try:
                formConcepts = [
                    x["doseFormName"]
                    for x in r["rxcuiStatusHistory"]["definitionalFeatures"][
                        "doseFormConcept"
                    ]
                ]
            except:
                pass
            if ingredient["denominatorUnit"] == "HR":
                d["MME_Conversion_Factor"] = 2400
            elif "Nasal Product" in doseForm:
                d["MME_Conversion_Factor"] = 160
            elif "Mucosal Product" in doseForm:
                d["MME_Conversion_Factor"] = 180
            elif "Buccal Film" in formConcepts:
                d["MME_Conversion_Factor"] = 180
            else:
                d["MME_Conversion_Factor"] = 130
            mme += d["MME_Conversion_Factor"] * d["Strength_Per_Unit"]
        elif baseName.lower() in MME_TABLE.keys():
            d["Strength_Per_Unit"] = float(value)
            d["MME_Conversion_Factor"] = MME_TABLE[baseName.lower()]
            mme += d["MME_Conversion_Factor"] * d["Strength_Per_Unit"]
    d["Calculated_MME"] = round(mme, 3)


def get_all_fields(NDC):
    d = {"NDC": NDC}
    rxcui = get_rxcui_from_ndc(NDC)
    if rxcui == None:
        return d
    get_rxterms(rxcui, d)
    class_id = get_pharma_class(rxcui, d)
    if class_id is not None:
        get_thera_class(class_id, d)
    calculate_MME(rxcui, d)
    dea_class = get_rxnorm_property(rxcui, "SCHEDULE")
    roman_numeral = ""
    if dea_class == "1":
        roman_numeral = "C-I"
    if dea_class == "2":
        roman_numeral = "C-II"
    if dea_class == "3":
        roman_numeral = "C-III"
    if dea_class == "4":
        roman_numeral = "C-IV"
    if dea_class == "5":
        roman_numeral = "C-V"
    d["DEA_Class"] = roman_numeral
    return d


if __name__ == "__main__":
    drugs = {}
    with open("rxnorm_cache.pickle", "rb") as inf:
        drugs = pickle.load(inf)

    i = 0
    with open("unique_ndc.csv", "r") as csv:
        for line in csv:
            ndc = line.strip()
            print("{} - {}".format(i, ndc))
            i += 1
            if ndc not in drugs.keys():
                try:
                    drug = get_all_fields(line.strip())
                    drugs[ndc] = drug
                    print(drug)
                except:
                    break

    with open("rxnorm_cache.pickle", "wb") as outf:
        pickle.dump(drugs, outf)

    drug_arr = []
    for key in drugs.keys():
        drug_arr.append(drugs[key])
    df = pd.DataFrame(drug_arr)
    df.to_csv("rxnorm_drugs.csv", index=False)
