import sys
from pathlib import Path
from enum import Enum

from rpd_tester.utils import *
from rpd_tester.map_objects import map_objects

# RPD Generation Test Report
results_data = {
    "generation_software_name": "",
    "generation_software_version": "",
    "modeling_software_name": "",
    "modeling_software_version": "",
    "schema_version": "",
    "ruleset_name": "",
    "ruleset_checking_specification_name": "",
    "test_case_reports": [],  # List of test case report dicts
}


class EvaluationCriteriaOptions(Enum):
    VALUE = "VALUE"
    PRESENT = "PRESENT"
    REFERENCE = "REFERENCE"
    QUANTITY = "QUANTITY"


class TestOutcomeOptions(Enum):
    MATCH = "MATCH"
    DIFFER = "DIFFER"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


# Test Case Report
def add_test_case_report(test_case_dir, generated_file_name):
    files_utilized = [
        f.name for f in test_case_dir.iterdir() if f.is_file() and f.suffix != ".json"
    ]
    test_case_report = {
        "test_id": test_case_dir.name,
        "generated_file_name": generated_file_name,
        "files_utilized": files_utilized,
        "specification_tests": [],
    }
    results_data["test_case_reports"].append(test_case_report)
    return test_case_report


# Specification Test
def add_specification_test(test_case_report, data_path, evaluation_criteria=""):
    specification_test = {
        "data_path": data_path,
        "evaluation_criteria": evaluation_criteria,
        "test_results": [],
    }
    test_case_report["specification_tests"].append(specification_test)
    return specification_test


# Test Result
def add_test_result(
        specification_test,
        generated_instance_id,
        reference_instance_id,
        test_outcome,
        notes="",
):
    data_element = specification_test["data_path"].split(".")[-1]
    test_result = {
        "generated_instance_id": generated_instance_id,  # if generated_instance_id else None,
        "reference_instance_id": (
            reference_instance_id if reference_instance_id else None
        ),
        "data_element": data_element,
        "test_outcome": test_outcome,
        "notes": notes,
    }
    specification_test["test_results"].append(test_result)
    return test_result


def load_json_file(file_path):
    """Loads JSON data from a file."""
    with open(file_path, "r") as file:
        return json.load(file)


def compare_json_values(
    spec,
    generated_values,
    reference_values,
    generated_ids,
    specification_test,
    object_id_map,
):
    """Compares a list of generated and reference JSON values based on the spec."""
    json_key_path = spec["json-key-path"]
    compare_value = spec.get("compare-value", True)
    tolerance = spec.get("tolerance", 0)

    warnings = []
    errors = []

    for i, generated_id in enumerate(generated_ids):
        if generated_id not in generated_values and i in generated_values:
            generated_id = i
        generated_value = generated_values[generated_id]
        reference_value = reference_values[generated_id]
        reference_id = object_id_map.get(generated_id)

        if generated_value is None and reference_value is not None:
            notes = f"Missing value for key '{json_key_path.split('.')[-1]}' at {generated_ids[i]}"
            add_test_result(
                specification_test,
                generated_id,
                reference_id,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            continue

        if isinstance(reference_value, dict):
            raise ValueError("json-test-key-path should not result in a dictionary.")

        elif isinstance(reference_value, list):
            # Reference value is a list. Set EvaluationCriteriaOptions to QUANTITY
            specification_test["evaluation_criteria"] = (
                EvaluationCriteriaOptions.QUANTITY.value
            )

            if len(generated_value) != len(reference_value):
                notes = f"List length mismatch at '{generated_ids[i]}' for key '{json_key_path.split('.')[-1]}'. Expected: {len(reference_value)}; got: {len(generated_value)}"
                add_test_result(
                    specification_test,
                    generated_id,
                    reference_id,
                    TestOutcomeOptions.DIFFER.value,
                )
                errors.append(notes)
                continue
            else:
                add_test_result(
                    specification_test,
                    generated_id,
                    reference_id,
                    TestOutcomeOptions.MATCH.value,
                )

            if compare_value:
                # Reference value is a list with value comparisons. Combine QUANTITY and VALUE
                specification_test["evaluation_criteria"] = (
                    EvaluationCriteriaOptions.VALUE.value
                )

                for j, (gen_item, ref_item) in enumerate(
                    zip(generated_value, reference_value)
                ):
                    if gen_item != ref_item:
                        notes = f"List element mismatch for {generated_ids[i]} at index [{j}]. Expected: {ref_item}; got: {gen_item}"
                        add_test_result(
                            specification_test,
                            generated_id,
                            reference_id,
                            TestOutcomeOptions.DIFFER.value,
                        )
                        errors.append(notes)
                continue

        elif isinstance(reference_value, str) and not compare_value:
            specification_test["evaluation_criteria"] = (
                EvaluationCriteriaOptions.REFERENCE.value
            )

        if compare_value is False:
            continue  # No comparison needed, just check for existence

        if reference_value is None and generated_value is None:
            continue  # Both values are None, no need to compare

        # Evaluate based on value comparison
        specification_test["evaluation_criteria"] = (
            EvaluationCriteriaOptions.VALUE.value
        )
        test_outcome = TestOutcomeOptions.NOT_IMPLEMENTED.value

        # Else: the values are strings, ints, or floats, and we need to compare them
        notes = ""
        does_match = compare_values(generated_value, reference_value, tolerance)
        if does_match:
            test_outcome = TestOutcomeOptions.MATCH.value
        if not does_match and reference_value is None:
            warnings.append(
                f"Extra data provided at '{generated_ids[i]}' for key '{json_key_path.split('.')[-1]}'. Expected: 'None'; got: '{generated_value}'"
            )
            # Avoid adding a test result when extra data is provided
            continue
        elif not does_match:
            notes = f"Value mismatch at '{generated_ids[i]}' for key '{json_key_path.split('.')[-1]}'. Expected: '{reference_value}'; got: '{generated_value}'"
            errors.append(notes)
            test_outcome = TestOutcomeOptions.DIFFER.value

        add_test_result(
            specification_test,
            generated_id,
            reference_id,
            test_outcome,
        )

    if not generated_ids:
        notes = f"No generated IDs found for key '{json_key_path.split('.')[-1]}'"
        add_test_result(
            specification_test,
            None,
            None,
            TestOutcomeOptions.DIFFER.value,
        )
        warnings.append(notes)

    return warnings, errors


def handle_special_cases(
    path_spec, object_id_map, generated_json, reference_json, specification_test
):
    warnings = []
    errors = []

    json_key_path = path_spec["json-key-path"]
    special_case = path_spec["special-case"]
    compare_value = path_spec.get("compare-value", True)
    tolerance = path_spec.get("tolerance", 0)

    specification_test["evaluation_criteria"] = (
        EvaluationCriteriaOptions.VALUE.value
        if compare_value
        else EvaluationCriteriaOptions.PRESENT.value
    )

    # Handle Special Case for design electric power based on design airflow (which is not a specified value)
    if special_case == "W/cfm":
        special_case_value = path_spec["special-case-value"]

        generated_supply_fans = [
            fan
            for sys_fans in find_all(
                "$.ruleset_model_descriptions[*].buildings[*].building_segments[*].heating_ventilating_air_conditioning_systems[*].fan_system.supply_fans",
                generated_json,
            )
            for fan in sys_fans
        ]
        compare_fan_power_warnings, compare_fan_power_errors = compare_fan_power(
            generated_supply_fans, special_case_value
        )
        if compare_fan_power_warnings:
            warnings.extend(compare_fan_power_warnings)
        if compare_fan_power_errors:
            errors.extend(compare_fan_power_errors)

    # Handle Special Case for design electric power based on design airflow (which is not a specified value)
    elif special_case == "W/GPM":
        special_case_value_dict = path_spec["special-case-value"]
        special_case_value = None

        generated_pumps = find_all(
            "$.ruleset_model_descriptions[*].pumps[*]",
            generated_json,
        )

        for pump in generated_pumps:
            pump_type = "primary"
            pump_id = pump.get("id")
            loop_id = pump.get("loop_or_piping")
            loop = find_all_with_field_value(
                "$.ruleset_model_descriptions[*].fluid_loops[*]",
                "id",
                loop_id,
                generated_json,
            )

            if not loop:
                pump_type = "secondary"
                loop = find_all_with_field_value(
                    "$.ruleset_model_descriptions[*].fluid_loops[*].child_loops[*]",
                    "id",
                    loop_id,
                    generated_json,
                )

            if not loop:
                errors.append(
                    f"Could not find loop with id '{loop_id}' for pump '{pump_id}'"
                )
                continue

            loop = loop[0]
            loop_type = loop.get("type")

            if loop_type == "COOLING" and pump_type == "primary":
                special_case_value = special_case_value_dict["PCHW"]
            elif loop_type == "COOLING" and pump_type == "secondary":
                special_case_value = special_case_value_dict["SCHW"]
            elif loop_type == "HEATING":
                special_case_value = special_case_value_dict["HW"]
            elif loop_type == "CONDENSER":
                special_case_value = special_case_value_dict["CW"]

            compare_pump_power_warnings, compare_pump_power_errors = compare_pump_power(
                pump, special_case_value
            )
            # Test mismatch if there are warnings from compare_pump_power
            if compare_pump_power_warnings:
                notes = ""
                for warn in compare_pump_power_warnings:
                    notes += f"{warn}\n"
                    warnings.extend(
                        f"Warning at {json_key_path.split('.')[-1]}: {warn}"
                    )
                add_test_result(
                    specification_test,
                    pump_id,
                    None,
                    TestOutcomeOptions.DIFFER.value,
                )
            if compare_pump_power_errors:
                errors.extend(
                    f"Error at {json_key_path.split('.')[-1]}: {err}"
                    for err in compare_pump_power_errors
                )

            # If no warnings or errors are produced from comparison, add MATCH test result
            if not compare_pump_power_warnings and not compare_pump_power_errors:
                # No reference ID since we are comparing the generated value to a predetermined special case value
                add_test_result(
                    specification_test,
                    pump_id,
                    None,
                    TestOutcomeOptions.MATCH.value,
                )

    # Handle Special Case for interior wall azimuths (which may be opposite due to the adjacent zone)
    elif special_case == "azimuth":
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_zones = get_zones_from_json(generated_json)

        generated_surfaces = find_all(
            json_key_path[
                : json_key_path.index("].", json_key_path.index("surfaces")) + 1
            ],
            generated_json,
        )

        # Iterate through the generated surfaces to populate data for each surface individually, ensuring correct alignment via object mapping
        for generated_surface in generated_surfaces:
            generated_surface_id = generated_surface["id"]
            reference_surface_id = object_id_map.get(generated_surface_id)

            if not reference_surface_id:
                errors.append(
                    f"Could not map '{generated_surface_id}' to a reference surface"
                )
                continue

            aligned_reference_surface = find_one(
                json_key_path[
                    : json_key_path.index("].", json_key_path.index("surfaces")) + 1
                ]
                + f"[?(@.id == '{reference_surface_id}')]",
                reference_json,
                None,
            )

            if not aligned_reference_surface:
                errors.append(
                    f"Could not find reference surface with id '{reference_surface_id}'"
                )
                continue

            generated_parent_zone = next(
                zone
                for zone in generated_zones
                if any(
                    surface["id"] == generated_surface_id
                    for surface in zone.get("surfaces", [])
                )
            )
            generated_parent_zone_id = generated_parent_zone["id"]
            reference_parent_zone_id = object_id_map.get(generated_parent_zone_id)

            generated_value = generated_surface.get(json_key_path.split(".")[-1])
            aligned_generated_values[generated_surface_id] = generated_value
            # Extract values from aligned surfaces using the specified key path
            if "surfaces[?(@" in json_key_path:
                aligned_reference_value = find_one(
                    json_key_path.replace(
                        "surfaces[?(",
                        f"surfaces[?(@.id == '{reference_surface_id}' & ",
                    ),
                    reference_json,
                    None,
                )
            else:
                aligned_reference_value = find_one(
                    json_key_path.replace(
                        "surfaces[*]",
                        f"surfaces[?(@.id == '{reference_surface_id}')]",
                    ),
                    reference_json,
                    None,
                )
            aligned_reference_values[generated_surface_id] = aligned_reference_value

            mismatched_wall_origin_adjacent_zone = (
                aligned_reference_surface.get("adjacent_zone")
                == reference_parent_zone_id
            ) != (generated_surface.get("adjacent_zone") == generated_parent_zone_id)
            if not (
                (
                    not mismatched_wall_origin_adjacent_zone
                    and aligned_reference_value == generated_value
                )
                or (
                    mismatched_wall_origin_adjacent_zone
                    and (aligned_reference_value + 180) % 360 == generated_value
                )
            ):
                expected_value = (
                    aligned_reference_value
                    if not mismatched_wall_origin_adjacent_zone
                    else (aligned_reference_value + 180) % 360
                )

                errors.append(
                    f"Value mismatch at '{generated_surface_id}' for key '{json_key_path.split('.')[-1]}': Expected '{expected_value}', got '{generated_value}'"
                )

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
        else:
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.MATCH.value,
            )

    elif special_case == "operation_lower_limit":
        sequence = path_spec.get("special-case-value", {}).get("sequence")

        if not sequence:
            raise ValueError(
                "Special case value for operation upper limit must include a controls sequence."
            )

        if sequence == "staged":
            generated_boilers = find_all(
                json_key_path[
                    : json_key_path.index("].", json_key_path.index("boilers")) + 1
                ],
                generated_json,
            )
            is_staged = True
            expected_lower_limit = 0.0

            # Sort by operation_lower_limit
            sorted_boilers = sorted(
                generated_boilers,
                key=lambda b: b.get("operation_lower_limit", float("inf")),
            )

            for boiler in sorted_boilers:
                boiler_id = boiler.get("id")
                lower_limit = boiler.get("operation_lower_limit", 0)
                rated_capacity = boiler.get("rated_capacity", 0)

                if not compare_values(lower_limit, expected_lower_limit, tolerance):
                    notes = f"{boiler_id} operation lower limit incorrect for staged operation. Expected: {expected_lower_limit}; got: {lower_limit}"
                    add_test_result(
                        specification_test,
                        boiler_id,
                        None,
                        TestOutcomeOptions.DIFFER.value,
                    )
                    warnings.append(notes)
                    is_staged = False
                else:
                    # Correct answer is not dependent on a reference value, so there is no reference ID
                    add_test_result(
                        specification_test,
                        boiler_id,
                        None,
                        TestOutcomeOptions.MATCH.value,
                    )

                expected_lower_limit += rated_capacity

            if not is_staged:
                warnings.append(
                    "Boilers are not staged based on operation lower limits."
                )

        else:
            raise ValueError(
                f"Logic for operation lower limit special case is not implemented for the '{sequence}' sequence."
            )

    elif special_case == "operation_upper_limit":
        sequence = path_spec.get("special-case-value", {}).get("sequence")

        if not sequence:
            raise ValueError(
                "Special case value for operation upper limit must include a controls sequence."
            )

        if sequence == "staged":
            generated_boilers = find_all(
                json_key_path[
                    : json_key_path.index("].", json_key_path.index("boilers")) + 1
                ],
                generated_json,
            )
            is_staged = True

            # Create list of (boiler, capacity) and sort by operation_upper_limit
            boilers_with_capacity = [
                (boiler, boiler.get("rated_capacity", 0))
                for boiler in generated_boilers
            ]
            sorted_boilers = sorted(
                boilers_with_capacity,
                key=lambda pair: pair[0].get("operation_upper_limit", float("inf")),
            )

            expected_upper_limit = 0.0
            for boiler, capacity in sorted_boilers:
                boiler_id = boiler.get("id")
                expected_upper_limit += capacity
                actual_upper_limit = boiler.get("operation_upper_limit", 0)

                if not compare_values(
                    actual_upper_limit, expected_upper_limit, tolerance
                ):
                    notes = f"{boiler_id} operation upper limit incorrect for staged operation. Expected: {expected_upper_limit}; got: {actual_upper_limit}"
                    add_test_result(
                        specification_test,
                        boiler_id,
                        None,
                        TestOutcomeOptions.DIFFER.value,
                    )
                    warnings.append(notes)
                    is_staged = False
                else:
                    add_test_result(
                        specification_test,
                        boiler_id,
                        None,
                        TestOutcomeOptions.MATCH.value,
                    )

            if not is_staged:
                warnings.append(
                    "Boilers are not staged based on operation upper limits."
                )

        else:
            raise ValueError(
                f"Logic for operation lower limit special case is not implemented for the '{sequence}' sequence."
            )

    return warnings, errors


def handle_ordered_comparisons(
    path_spec, object_id_map, reference_json, generated_json, specification_test
):
    json_key_path = path_spec["json-key-path"]
    compare_value = path_spec.get("compare-value", True)

    specification_test["evaluation_criteria"] = (
        EvaluationCriteriaOptions.VALUE.value
        if compare_value
        else EvaluationCriteriaOptions.PRESENT.value
    )

    warnings = []
    errors = []

    # Handle comparison of data derived from zones which may not be in the same order as the reference zones
    if (
        "zones[" in json_key_path
        and "surfaces[" not in json_key_path
        and "terminals[" not in json_key_path
    ):
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_zones = get_zones_from_json(generated_json)
        generated_zone_ids = [zone["id"] for zone in generated_zones]

        # Populate data for each zone individually and ensure correct alignment via object mapping
        for generated_zone in generated_zones:
            generated_zone_id = generated_zone["id"]
            reference_zone_id = object_id_map[generated_zone_id]

            zone_data_path = json_key_path[
                (json_key_path.index("].", json_key_path.index("zones")) + 2) :
            ]
            generated_value = find_one(zone_data_path, generated_zone)
            aligned_generated_values[generated_zone_id] = generated_value
            # Extract values from aligned zones using the specified key path
            aligned_reference_value = find_one(
                json_key_path.replace(
                    "zones[*]", f"zones[?(@.id == '{reference_zone_id}')]"
                ),
                reference_json,
                None,
            )

            aligned_reference_values[generated_zone_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_zone_ids,
            specification_test,
            object_id_map,
        )
        errors.extend(general_comparison_errors)

    elif "surfaces[" in json_key_path:
        # Handle comparison of data derived from surfaces which may not be in the same order as the reference surfaces
        aligned_generated_values = {}
        aligned_reference_values = {}

        # Populate data for each surface individually and ensure correct alignment via object mapping
        generated_surfaces = find_all(
            # Extract the key path for the surface (everything before surfaces[]. )
            json_key_path[
                : json_key_path.index("].", json_key_path.index("surfaces")) + 1
            ],
            generated_json,
        )
        generated_surface_ids = [surface["id"] for surface in generated_surfaces]

        for generated_surface in generated_surfaces:
            generated_surface_id = generated_surface["id"]
            reference_surface_id = object_id_map.get(generated_surface_id)

            # Extract the key path for the surface data (everything after surfaces[]. )
            generated_value = find_one(
                json_key_path[
                    json_key_path.index("].", json_key_path.index("surfaces")) + 2 :
                ],
                generated_surface,
            )
            aligned_generated_values[generated_surface_id] = generated_value

            # Extract values from aligned surfaces using the specified key path
            if "surfaces[?(@" in json_key_path:
                aligned_reference_value = find_one(
                    json_key_path.replace(
                        "surfaces[?(",
                        f"surfaces[?(@.id == '{reference_surface_id}' & ",
                    ),
                    reference_json,
                    None,
                )
            else:
                aligned_reference_value = find_one(
                    json_key_path.replace(
                        "surfaces[*]",
                        f"surfaces[?(@.id == '{reference_surface_id}')]",
                    ),
                    reference_json,
                    None,
                )

            aligned_reference_values[generated_surface_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_surface_ids,
            specification_test,
            object_id_map,
        )
        warnings.extend(general_comparison_warnings)
        errors.extend(general_comparison_errors)

    elif "terminals[" in json_key_path:
        # Handle comparison of data derived from surfaces which may not be in the same order as the reference surfaces
        aligned_generated_values = {}
        aligned_reference_values = {}

        # Populate data for each surface individually and ensure correct alignment via object mapping
        generated_terminals = find_all(
            # Extract the key path for the surface (everything before surfaces[]. )
            json_key_path[
                : json_key_path.index("].", json_key_path.index("terminals")) + 1
            ],
            generated_json,
        )
        generated_terminal_ids = [terminal["id"] for terminal in generated_terminals]

        for generated_terminal in generated_terminals:
            generated_terminal_id = generated_terminal["id"]
            reference_terminal_id = object_id_map.get(generated_terminal_id)

            # Extract the key path for the terminal data (everything after terminals[]. )
            generated_value = find_one(
                json_key_path[
                    json_key_path.index("].", json_key_path.index("terminals")) + 2 :
                ],
                generated_terminal,
            )
            aligned_generated_values[generated_terminal_id] = generated_value

            # Extract values from aligned terminals using the specified key path
            if "terminals[?(@" in json_key_path:
                aligned_reference_value = find_one(
                    json_key_path.replace(
                        "terminals[?(",
                        f'terminals[?(@.id=="{reference_terminal_id}" & ',
                    ),
                    reference_json,
                    None,
                )
            else:
                aligned_reference_value = find_one(
                    json_key_path.replace(
                        "terminals[*]",
                        f"terminals[?(@.id == '{reference_terminal_id}')]",
                    ),
                    reference_json,
                    None,
                )

            aligned_reference_values[generated_terminal_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_terminal_ids,
            specification_test,
            object_id_map,
        )
        warnings.extend(general_comparison_warnings)
        errors.extend(general_comparison_errors)

    elif "heating_ventilating_air_conditioning_systems[" in json_key_path:
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_hvacs = find_all(
            json_key_path[
                : json_key_path.index(
                    "].",
                    json_key_path.index("heating_ventilating_air_conditioning_systems"),
                )
                + 1
            ],
            generated_json,
        )
        generated_hvac_ids = [hvac["id"] for hvac in generated_hvacs]

        # Populate data for each zone individually and ensure correct alignment via object mapping
        for generated_hvac in generated_hvacs:
            generated_hvac_id = generated_hvac["id"]
            reference_hvac_id = object_id_map.get(generated_hvac_id)

            if not reference_hvac_id:
                continue

            hvac_data_path = json_key_path[
                json_key_path.index(
                    "].",
                    json_key_path.index("heating_ventilating_air_conditioning_systems"),
                )
                + 2 :
            ]
            generated_value = find_one(hvac_data_path, generated_hvac)
            aligned_generated_values[generated_hvac_id] = generated_value
            # Extract values from aligned zones using the specified key path
            aligned_reference_value = find_one(
                json_key_path.replace(
                    "heating_ventilating_air_conditioning_systems[*]",
                    f"heating_ventilating_air_conditioning_systems[?(@.id == '{reference_hvac_id}')]",
                ),
                reference_json,
                None,
            )

            aligned_reference_values[generated_hvac_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_hvac_ids,
            specification_test,
            object_id_map,
        )
        errors.extend(general_comparison_errors)

    elif "boilers[" in json_key_path:
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_boilers = find_all(
            json_key_path[
                : json_key_path.index("].", json_key_path.index("boilers")) + 1
            ],
            generated_json,
        )
        generated_boiler_ids = [boiler["id"] for boiler in generated_boilers]

        for generated_boiler in generated_boilers:
            generated_boiler_id = generated_boiler["id"]
            reference_boiler_id = object_id_map.get(generated_boiler_id)

            if not reference_boiler_id:
                continue

            boiler_data_path = json_key_path[
                json_key_path.index("].", json_key_path.index("boilers")) + 2 :
            ]
            generated_value = find_one(boiler_data_path, generated_boiler)
            aligned_generated_values[generated_boiler_id] = generated_value

            aligned_reference_value = find_one(
                json_key_path.replace(
                    "boilers[*]",
                    f"boilers[?(@.id == '{reference_boiler_id}')]",
                ),
                reference_json,
                None,
            )

            aligned_reference_values[generated_boiler_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_boiler_ids,
            specification_test,
            object_id_map,
        )
        errors.extend(general_comparison_errors)

    elif "chillers[" in json_key_path:
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_chillers = find_all(
            json_key_path[
                : json_key_path.index("].", json_key_path.index("chillers")) + 1
            ],
            generated_json,
        )
        generated_chiller_ids = [chiller["id"] for chiller in generated_chillers]

        for generated_chiller in generated_chillers:
            generated_chiller_id = generated_chiller["id"]
            reference_chiller_id = object_id_map.get(generated_chiller_id)

            if not reference_chiller_id:
                continue

            chiller_data_path = json_key_path[
                json_key_path.index("].", json_key_path.index("chillers")) + 2 :
            ]
            generated_value = find_one(chiller_data_path, generated_chiller)
            aligned_generated_values[generated_chiller_id] = generated_value

            aligned_reference_value = find_one(
                json_key_path.replace(
                    "chillers[*]",
                    f"chillers[?(@.id == '{reference_chiller_id}')]",
                ),
                reference_json,
                None,
            )

            aligned_reference_values[generated_chiller_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_chiller_ids,
            specification_test,
            object_id_map,
        )
        errors.extend(general_comparison_errors)

    elif "heat_rejections[" in json_key_path:
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_heat_rejections = find_all(
            json_key_path[
                : json_key_path.index("].", json_key_path.index("heat_rejections")) + 1
            ],
            generated_json,
        )
        generated_heat_rejection_ids = [
            heat_rejection["id"] for heat_rejection in generated_heat_rejections
        ]

        for generated_heat_rejection in generated_heat_rejections:
            generated_heat_rejection_id = generated_heat_rejection["id"]
            reference_heat_rejection_id = object_id_map.get(generated_heat_rejection_id)

            if not reference_heat_rejection_id:
                continue

            heat_rejection_data_path = json_key_path[
                json_key_path.index("].", json_key_path.index("heat_rejections")) + 2 :
            ]
            generated_value = find_one(
                heat_rejection_data_path, generated_heat_rejection
            )
            aligned_generated_values[generated_heat_rejection_id] = generated_value

            aligned_reference_value = find_one(
                json_key_path.replace(
                    "heat_rejections[*]",
                    f"heat_rejections[?(@.id == '{reference_heat_rejection_id}')]",
                ),
                reference_json,
                None,
            )

            aligned_reference_values[generated_heat_rejection_id] = (
                aligned_reference_value
            )

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_heat_rejection_ids,
            specification_test,
            object_id_map,
        )
        errors.extend(general_comparison_errors)

    elif "fluid_loops[" in json_key_path:
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_fluid_loops = find_all(
            json_key_path[
                : json_key_path.index("].", json_key_path.index("fluid_loops")) + 1
            ],
            generated_json,
        )
        generated_fluid_loop_ids = [
            fluid_loop["id"] for fluid_loop in generated_fluid_loops
        ]

        for generated_fluid_loop in generated_fluid_loops:
            generated_fluid_loop_id = generated_fluid_loop["id"]
            reference_fluid_loop_id = object_id_map.get(generated_fluid_loop_id)

            if not reference_fluid_loop_id:
                continue

            fluid_loop_data_path = json_key_path[
                json_key_path.index("].", json_key_path.index("fluid_loops")) + 2 :
            ]
            generated_value = find_one(fluid_loop_data_path, generated_fluid_loop)
            aligned_generated_values[generated_fluid_loop_id] = generated_value

            aligned_reference_value = find_one(
                json_key_path.replace(
                    "fluid_loops[*]",
                    f"fluid_loops[?(@.id == '{reference_fluid_loop_id}')]",
                ),
                reference_json,
                None,
            )

            aligned_reference_values[generated_fluid_loop_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_fluid_loop_ids,
            specification_test,
            object_id_map,
        )
        errors.extend(general_comparison_errors)

    elif "pumps[" in json_key_path:
        aligned_generated_values = {}
        aligned_reference_values = {}

        generated_pumps = find_all(
            json_key_path[
                : json_key_path.index("].", json_key_path.index("pumps")) + 1
            ],
            generated_json,
        )
        generated_pump_ids = [pump["id"] for pump in generated_pumps]

        for generated_pump in generated_pumps:
            generated_pump_id = generated_pump["id"]
            reference_pump_id = object_id_map.get(generated_pump_id)

            if not reference_pump_id:
                continue

            pump_data_path = json_key_path[
                json_key_path.index("].", json_key_path.index("pumps")) + 2 :
            ]
            generated_value = find_one(pump_data_path, generated_pump)
            aligned_generated_values[generated_pump_id] = generated_value

            aligned_reference_value = find_one(
                json_key_path.replace(
                    "pumps[*]",
                    f"pumps[?(@.id == '{reference_pump_id}')]",
                ),
                reference_json,
                None,
            )

            aligned_reference_values[generated_pump_id] = aligned_reference_value

        if all(value is None for value in aligned_generated_values.values()):
            notes = f"Missing key {json_key_path.split('.')[-1]}"
            add_test_result(
                specification_test,
                None,
                None,
                TestOutcomeOptions.NOT_IMPLEMENTED.value,
            )
            warnings.append(notes)
            return warnings, errors

        general_comparison_warnings, general_comparison_errors = compare_json_values(
            path_spec,
            aligned_generated_values,
            aligned_reference_values,
            generated_pump_ids,
            specification_test,
            object_id_map,
        )
        errors.extend(general_comparison_errors)

    return warnings, errors


def handle_unordered_comparisons(
    path_spec, reference_json, generated_json, specification_test, object_id_map
):
    json_key_path = path_spec["json-key-path"]
    compare_value = path_spec.get("compare-value", True)

    specification_test["evaluation_criteria"] = (
        EvaluationCriteriaOptions.VALUE.value
        if compare_value
        else EvaluationCriteriaOptions.PRESENT.value
    )

    warnings = []
    errors = []
    # The order will be the same for the generated and reference values, or the order does not matter in the tests
    if ".".join(json_key_path.split(".")[:-1]) == "$":
        generated_value_parents = [generated_json]
    else:
        generated_value_parents = find_all(
            ".".join(json_key_path.split(".")[:-1]), generated_json
        )
    generated_value_parent_ids = [
        # Important to use get() here to avoid key errors where objects have no ID such as weather
        value.get("id")
        for value in generated_value_parents
    ]
    generated_values = find_all(json_key_path, generated_json)
    generated_values = {index: value for index, value in enumerate(generated_values)}
    reference_values = find_all(json_key_path, reference_json)
    reference_values = {index: value for index, value in enumerate(reference_values)}

    if all(value is None for value in generated_values):
        notes = f"Missing key {json_key_path.split('.')[-1]}"
        add_test_result(
            specification_test,
            None,
            None,
            TestOutcomeOptions.NOT_IMPLEMENTED.value,
        )
        warnings.append(notes)
        return warnings, errors

    general_comparison_warnings, general_comparison_errors = compare_json_values(
        path_spec,
        generated_values,
        reference_values,
        generated_value_parent_ids,
        specification_test,
        object_id_map,
    )
    warnings.extend(general_comparison_warnings)
    errors.extend(general_comparison_errors)

    return warnings, errors


def run_file_comparison(
    spec_file, generated_json_file, reference_json_file, test_case_report
):
    """Compares generated and reference JSON files according to the spec."""
    spec = load_json_file(spec_file)
    json_test_key_paths = spec.get("json-test-key-paths", [])

    generated_json = load_json_file(generated_json_file)
    reference_json = load_json_file(reference_json_file)

    warnings = []
    errors = []

    object_id_map, map_warnings, map_errors = map_objects(
        generated_json, reference_json
    )
    warnings.extend(map_warnings)
    errors.extend(map_errors)
    if not object_id_map:
        return warnings, errors

    # Once maps have been defined, iterate through the test specs
    for path_spec in json_test_key_paths:
        json_key_path = path_spec["json-key-path"]
        special_case = path_spec.get("special-case")

        # Add specification test to the report
        specification_test = add_specification_test(test_case_report, json_key_path)

        # Handle any cases that require special logic
        if special_case:
            special_case_warnings, special_case_errors = handle_special_cases(
                path_spec,
                object_id_map,
                generated_json,
                reference_json,
                specification_test,
            )
            warnings.extend(special_case_warnings)
            errors.extend(special_case_errors)

        # Begin the General Comparison Methodology
        else:

            # Handle comparison of data derived from objects which may not be in the same order as the reference objects
            if any(
                group in json_key_path
                for group in [
                    "zones[",
                    "surfaces[",
                    "terminals[",
                    "heating_ventilating_air_conditioning_systems[",
                    "boilers[",
                    "chillers[",
                    "heat_rejections[",
                    "fluid_loops[",
                    "pumps[",
                ]
            ):
                (
                    ordered_comparison_warnings,
                    ordered_comparison_errors,
                ) = handle_ordered_comparisons(
                    path_spec,
                    object_id_map,
                    reference_json,
                    generated_json,
                    specification_test,
                )
                warnings.extend(ordered_comparison_warnings)
                errors.extend(ordered_comparison_errors)

            # Handle comparison of data that is not dependent on order
            else:
                (
                    unordered_comparison_warnings,
                    unordered_comparison_errors,
                ) = handle_unordered_comparisons(
                    path_spec,
                    reference_json,
                    generated_json,
                    specification_test,
                    object_id_map,
                )
                warnings.extend(unordered_comparison_warnings)
                errors.extend(unordered_comparison_errors)

    return warnings, errors


def run_comparison_for_all_tests(test_dir: Path):
    """Runs JSON comparison for all test cases in the test directory."""
    reference_dir = test_dir.parent / "reference_rpds"
    spec_dir = test_dir.parent / "comparison_specs"

    total_errors = 0

    for test_case_dir in test_dir.iterdir():
        if not test_case_dir.is_dir():
            continue

        test = test_case_dir.name

        generated_json_file = next(
            (f for f in test_case_dir.iterdir() if f.suffix == ".json"), None
        )
        if not generated_json_file:
            continue

        spec_file = spec_dir / f"{test} spec.json"
        reference_json_file = reference_dir / f"{test}.json"

        if (
            generated_json_file.is_file()
            and spec_file.is_file()
            and reference_json_file.is_file()
        ):

            test_case_report = add_test_case_report(
                test_case_dir, generated_json_file.name
            )
            print(f"Running comparison for {test}...")
            warnings, errors = run_file_comparison(
                spec_file,
                generated_json_file,
                reference_json_file,
                test_case_report,
            )
            print_results(test, warnings, errors)
            total_errors += len(errors)

        else:
            print(
                f"Skipping {test} because it does not contain the required files."
            )
            continue

    save_to_json_file()

    if total_errors > 0:
        sys.exit(1)


def print_results(test, warnings, errors):
    """Prints the comparison results."""
    if warnings:
        print(
            f"""----------------------------
    Warnings for {test}:
----------------------------"""
        )
        for warning in warnings:
            print(f"{warning}")
    if errors:
        print(
            f"""----------------------------
    Errors for {test}:
----------------------------"""
        )
        for error in errors:
            print(f"{error}")


def save_to_json_file():
    file_path = "rpd_test_results.json"

    print(f"\nSaving results to {file_path}...")
    with open(file_path, "w") as test_output_file:
        json.dump(results_data, test_output_file, indent=4)
