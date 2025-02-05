from enum import verify

import pydicom, argparse
from pydicom.uid import generate_uid
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.tag import Tag


def iterate_content_sequence(content_sequence, level=0):
    """Recursively iterate over the content sequence of a DICOM Structured Report."""
    for item in content_sequence:
        # Extract Concept Name (if available) and Value
        concept_name = item.ConceptNameCodeSequence[0].CodeMeaning if 'ConceptNameCodeSequence' in item else "Unknown"
        value_type = item.ValueType

        if level == 0 and concept_name != 'Image Measurements':
            continue

        # if level == 0 and concept_name == 'Image Measurements':
        #     print(len(item.ContentSequence))
        #     print(type(item.ContentSequence))

        # Extract the actual value if it exists
        value = None
        if value_type == "TEXT":
            value = item.TextValue
        elif value_type == "NUM":
            value = f"{item.MeasuredValueSequence[0].NumericValue} {item.MeasuredValueSequence[0].MeasurementUnitsCodeSequence[0].CodeMeaning}"
        elif value_type == "CODE":
            value = item.ConceptCodeSequence[0].CodeMeaning
        elif value_type == "DATETIME":
            value = item.DateTime
        elif value_type == "DATE":
            value = item.Date
        elif value_type == "TIME":
            value = item.Time
        elif value_type == "UIDREF":
            value = item.UID

        # Print extracted information
        indent = "  " * level
        print(f"{indent}- {concept_name} [{value_type}]: {value}")

        # Recursively process nested ContentSequence
        if hasattr(item, "ContentSequence"):
            iterate_content_sequence(item.ContentSequence, level + 1)


# def extract_tracking_uids(ds) -> set:
#     uids = set()
#     for item in ds.ContentSequence:
#         concept_name = item.ConceptNameCodeSequence[0].CodeMeaning if 'ConceptNameCodeSequence' in item else "Unknown"
#         if concept_name == 'Image Measurements':
#             for item2 in item.ContentSequence:
#                 if not hasattr(item2, "ContentSequence"):
#                     continue
#                 for item3 in item2.ContentSequence:
#                     concept_name = item3.ConceptNameCodeSequence[0].CodeMeaning if 'ConceptNameCodeSequence' in item3 else "Unknown"
#                     value_type = item3.ValueType
#                     if concept_name == 'Tracking Unique Identifier' and value_type == 'UIDREF':
#                         uids.add(item3.UID)
#     return uids

def extract_observation_uids(ds) -> list:
    uids = []
    for item in ds.ContentSequence:
        concept_name = item.ConceptNameCodeSequence[0].CodeMeaning if 'ConceptNameCodeSequence' in item else "Unknown"
        if concept_name == 'Image Measurements':
            for item2 in item.ContentSequence:
                if not hasattr(item2, "ContentSequence"):
                    continue
                for item3 in item2.ContentSequence:
                    if 'ObservationUID' in item3:
                        uids.append(item3.ObservationUID)
    return uids


def delete_findings_by_index(ds, indexes_to_remove : list):
    for item in ds.ContentSequence:
        concept_name = item.ConceptNameCodeSequence[0].CodeMeaning if 'ConceptNameCodeSequence' in item else "Unknown"
        if concept_name == 'Image Measurements':
            for index in indexes_to_remove:
                del item.ContentSequence[index]
    return ds


def get_item_delimitation():
    return pydicom.DataElement(Tag(0xFFFE, 0xE00D), 'UL', 0)


def get_new_sequence(items : list = None):
    sequence = Sequence(items)
    sequence.is_undefined_length = True
    return sequence


def add_item_to_content_sequence(
        content_sequence : Sequence,
        relationship_type: str,
        value_type: str,
        code_value1: str,
        coding_scheme1: str,
        code_meaning1: str,
        code_value2: str = None,
        coding_scheme2: str = None,
        code_meaning2: str = None
    ) -> Dataset:
    parent_item = Dataset()
    parent_item.RelationshipType = relationship_type
    parent_item.ValueType = value_type

    child_item1 = Dataset()
    child_item1.CodeValue = code_value1
    child_item1.CodingSchemeDesignator = coding_scheme1
    child_item1.CodeMeaning = code_meaning1

    parent_item.ConceptNameCodeSequence = get_new_sequence([child_item1])

    if code_value2:
        child_item2 = Dataset()
        child_item2.CodeValue = code_value2
        child_item2.CodingSchemeDesignator = coding_scheme2
        child_item2.CodeMeaning = code_meaning2
        parent_item.ConceptCodeSequence = get_new_sequence([child_item2])

    content_sequence.append(parent_item)
    return parent_item



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Given an IHE AIR input SR (TID 1500), this script will produce two output files: one with filtered finds, and one with approval status')
    parser.add_argument('-i','--input', type=str, nargs='?', required=True, help="Path to input DICOM SR")
    parser.add_argument('-f', '--filtered', type=str, nargs='?', required=True, help="Path to output *filtered* DICOM SR")
    # TODO Assessment SR should have references to the rejected findings
    parser.add_argument('-a', '--assessment', type=str, nargs='?', required=True, help="Path to output *assessment status* DICOM SR")
    args = parser.parse_args()

    input_sr = pydicom.dcmread(args.input)
    if hasattr(input_sr, "ContentSequence"):
        print("Valid Content Sequence found in the DICOM SR.")
        iterate_content_sequence(input_sr.ContentSequence)
    else:
        print("No Content Sequence found in the DICOM SR.")

    # Create a copy without some of the findings then generate new UIDs and write file
    filtered_sr = delete_findings_by_index(pydicom.dcmread(args.input), [0,7])
    filtered_sr.SOPInstanceUID = generate_uid()
    filtered_sr.SeriesInstanceUID = generate_uid()
    filtered_sr.save_as(args.filtered, enforce_file_format=True)

    # Extract all observation UIDs
    old_observation_uids = extract_observation_uids(input_sr)
    new_observation_uids = extract_observation_uids(filtered_sr)
    print(new_observation_uids)

    # Begin constructing the assessment SR
    assessment_sr = pydicom.dcmread(args.input)
    assessment_sr.SOPInstanceUID = generate_uid()
    assessment_sr.SeriesInstanceUID = generate_uid()
    del assessment_sr.ContentSequence

    # Append to Contributing Equipment Sequence
    contributing_equipment = Dataset()
    contributing_equipment.Manufacturer = "Mohannad Hussain"
    contributing_equipment.ManufacturerModelName = "Python script"
    contributing_equipment.SoftwareVersions = "0.0.1"
    contributing_equipment.ContributionDateTime = pydicom.valuerep.DT("20250204120000")
    contributing_equipment.ContributionDescription = "Reference IHE profile implementation"
    purpose_coding = Dataset()
    purpose_coding.CodeValue = '109102'
    purpose_coding.CodingSchemeDesignator = 'DCM'
    purpose_coding.CodeMeaning = 'Processing Equipment'
    contributing_equipment.PurposeOfReferenceCodeSequence = Sequence([purpose_coding])
    assessment_sr.ContributingEquipmentSequence.append(contributing_equipment)

    # Verification attributes
    assessment_sr.VerificationFlag = "UNVERIFIED"
    verifying_observer = Dataset()
    verifying_observer.VerifyingObserverName = "Hussain^Mohannad"
    #TODO Verifying Observer Identification Code Sequence
    verifying_observer.VerifyingOrganization = "IHE Reference Implementation"
    verifying_observer.VerificationDateTime = pydicom.valuerep.DT("20250204120000")
    assessment_sr.VerifyingObserverSequence = Sequence([verifying_observer])

    # Referenced Instance Sequence
    ref_updated_sr = Dataset()
    ref_updated_sr.ReferencedSOPClassUID = filtered_sr.SOPClassUID
    ref_updated_sr.ReferencedSOPInstanceUID = filtered_sr.SOPInstanceUID
    ref_updated_sr.PurposeOfReferenceCodeSequence = Sequence([Dataset()])
    ref_updated_sr.PurposeOfReferenceCodeSequence[0].CodeValue = "AIRAI_24"
    ref_updated_sr.PurposeOfReferenceCodeSequence[0].CodingSchemeDesignator = "99IHE"
    ref_updated_sr.PurposeOfReferenceCodeSequence[0].CodeMeaning = "Assessed AI Result Object"

    ref_original_sr = Dataset()
    ref_original_sr.ReferencedSOPClassUID = input_sr.SOPClassUID
    ref_original_sr.ReferencedSOPInstanceUID = input_sr.SOPInstanceUID
    ref_original_sr.PurposeOfReferenceCodeSequence = Sequence([Dataset()])
    ref_original_sr.PurposeOfReferenceCodeSequence[0].CodeValue = "AIRAI_21"
    ref_original_sr.PurposeOfReferenceCodeSequence[0].CodingSchemeDesignator = "99IHE"
    ref_original_sr.PurposeOfReferenceCodeSequence[0].CodeMeaning = "Original AI Result Object"

    assessment_sr.ReferencedInstanceSequence = Sequence([ref_updated_sr, ref_original_sr])

    # AI Validation Result Root
    assessment_sr.ContentSequence = Sequence()

    root_node = Dataset()
    root_node.CodeValue = 'AIRAI_01'
    root_node.CodingSchemeDesignator = '99IHE'
    root_node.CodeMeaning = 'Approval Status Object'
    assessment_sr.ContentSequence.append(root_node)

    # Add language code (optional)
    add_item_to_content_sequence(
        content_sequence=assessment_sr.ContentSequence,
        relationship_type="HAS CONCEPT MOD",
        value_type="CODE",
        code_value1="121049",
        coding_scheme1="DCM",
        code_meaning1="Language of Content Item and Descendants",
        code_value2="eng",
        coding_scheme2="RFC5646",
        code_meaning2="English"
    )

    # TODO Observer Context

    # Result Assessment Portion - ie Meat & Potatoes
    result_assessment = add_item_to_content_sequence(
        content_sequence=assessment_sr.ContentSequence,
        relationship_type="CONTAINS",
        value_type="CONTAINER",
        code_value1="AIRAI_02",
        coding_scheme1="99IHE",
        code_meaning1="Result Assessment"
    )
    # TODO repeat for every finding?!?
    result_assessment.ContentSequence = get_new_sequence()
    add_item_to_content_sequence(
        content_sequence=result_assessment.ContentSequence,
        relationship_type="CONTAINS",
        value_type="CODE",
        code_value1="AIRAI_03",
        coding_scheme1="99IHE",
        code_meaning1="Result Type",
        code_value2="AIR004",
        coding_scheme2="99IHE",
        code_meaning2="Referenced Observation"
    )
    add_item_to_content_sequence(
        content_sequence=result_assessment.ContentSequence,
        relationship_type="CONTAINS",
        value_type="COMPOSITE",
        code_value1="AIRAI_04",
        coding_scheme1="99IHE",
        code_meaning1="Referenced Instance"
    )
    add_item_to_content_sequence(
        content_sequence=result_assessment.ContentSequence,
        relationship_type="CONTAINS",
        value_type="UIDREF",
        code_value1="AIR005",
        coding_scheme1="99IHE",
        code_meaning1="Referenced Observation UID"
    )
    assessment_status = add_item_to_content_sequence(
        content_sequence=result_assessment.ContentSequence,
        relationship_type="CONTAINS",
        value_type="CODE",
        code_value1="AIRAI_06",
        coding_scheme1="99IHE",
        code_meaning1="Result Assessment Status",
        code_value2="AIRAI_13",
        coding_scheme2="99IHE",
        code_meaning2="Unreviewed"
    )
    assessment_status.ContentSequence = get_new_sequence()
    add_item_to_content_sequence(
        content_sequence=assessment_status.ContentSequence,
        relationship_type="HAS CONCEPT MOD",
        value_type="CODE",
        code_value1="AIRAI_07",
        coding_scheme1="99IHE",
        code_meaning1="Assessment Scope",
        code_value2="AIRAI_17",
        coding_scheme2="99IHE",
        code_meaning2="Clinically relevant"
    )
    add_item_to_content_sequence(
        content_sequence=assessment_status.ContentSequence,
        relationship_type="HAS CONCEPT MOD",
        value_type="CODE",
        code_value1="AIRAI_08",
        coding_scheme1="99IHE",
        code_meaning1="Modification Scope",
        code_value2="AIRAI_19",
        coding_scheme2="99IHE",
        code_meaning2="Accepted after Modification"
    )

    # Save the file to disk
    assessment_sr.save_as(args.assessment, enforce_file_format=True)


