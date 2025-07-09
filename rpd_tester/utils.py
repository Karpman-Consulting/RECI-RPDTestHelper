import re
from jsonpath_ng.ext import parse
import json
import math
from difflib import get_close_matches
from itertools import chain
from typing import TypedDict


class ZonesTerminalsServedByHVACSys(TypedDict):
    terminal_list: list[str]
    zone_list: list[str]


class SurfacesWithConstructionAssigned(TypedDict):
    exterior_walls: int
    rooves: int
    below_grade_surfaces: int
    interior_surfaces: int
    primary_layers_length: int
    framing_layers_length: int
    u_factor: float | None
    c_factor: float | None
    f_factor: float | None


def ensure_root(jpath):
    return jpath if jpath.startswith("$") else "$." + jpath


def split_path(jpath):
    # If the path starts with "$.", remove it
    if jpath.startswith("$."):
        jpath = jpath[2:]

    result = []
    current_segment = []
    bracket_depth = 0

    for char in jpath:
        if char == "[":
            bracket_depth += 1
            current_segment.append(char)
        elif char == "]":
            bracket_depth -= 1
            current_segment.append(char)
        elif char == "." and bracket_depth == 0:
            # We are at a top-level dot, split here
            segment_str = "".join(current_segment).strip()
            if segment_str:
                result.append(segment_str)
            current_segment = []
        else:
            current_segment.append(char)

    # Add the last segment if it exists
    segment_str = "".join(current_segment).strip()
    if segment_str:
        result.append(segment_str)
    return result


def find_all(jpath, obj):
    # Regex to identify array index patterns like [*], [0], [1], etc.
    bracket_pattern = re.compile(r"\[([^]]*)]")

    def parse_path_segment(segment):
        """
        Given a path segment (like "surfaces[*][?(@.adjacent_to == 'EXTERIOR')]"),
        split it into a list of operations:

        For example:
        "surfaces[*][?(@.adjacent_to == 'EXTERIOR')]" ->
        [("key", "surfaces"), ("index", "*"), ("filter", "@.adjacent_to == 'EXTERIOR'")]
        """
        parts = []
        m = bracket_pattern.split(segment)
        base_key = m[0]
        if base_key:
            parts.append(("key", base_key))

        for i in range(1, len(m)):
            content = m[i].strip()
            if content == "":
                continue
            if content.startswith("?(") and content.endswith(")"):
                # Filter condition
                condition = content[2:-1].strip()
                parts.append(("filter", condition))
            else:
                parts.append(("index", content))

        return parts

    def evaluate_filter_condition(obj_inst, condition_str):
        """
        Evaluate a filter condition string against obj.
        Conditions can have `@.field == "value"` format
        and multiple conditions joined by "and".

        Handle @.field references, equality checks, and string values.
        """

        # Filter conditions look like: @.field == 'value'
        condition_str = condition_str.replace("==", "=")

        # Split by ' and ' to handle multiple conditions
        conditions = [c.strip() for c in condition_str.split(" and ")]

        def evaluate_single_condition(cond):
            # Pattern: @.field = 'value'
            match = re.match(r'@\.(\w+)\s*=\s*(["\'])(.*?)\2', cond)
            if not match:
                # If parsing fails, skip this condition (return False)
                return False
            field, _, value = match.groups()
            # Check if field is in (obj_inst and equals value
            return (field in obj_inst) and (obj_inst[field] == value)

        # All conditions must be True
        return all(evaluate_single_condition(c) for c in conditions)

    def recursive_find(parts, current_obj):
        """
        parts is a list of segments, each segment is a list of operations like:
        [("key","ruleset_model_descriptions"),("index","*")]
        Process them step-by-step.
        """
        if not parts:
            return [current_obj]

        segment = parts[0]
        results = [current_obj]

        for op_type, value in segment:
            key = value.split("[")[0].split("==")[0]
            new_results = []
            if op_type == "key":
                # For each object in results, fetch the value for the given key if it's a dict
                for r in results:
                    if isinstance(r, dict) and key in r:
                        new_results.append(r[key])
                    else:
                        # Key not found or r is not a dict, no results
                        pass

            elif op_type == "index":

                for r in results:

                    if isinstance(r, list):
                        if value == "*":
                            new_results.extend(r)

                        else:
                            try:
                                # Numeric index
                                idx = int(value)
                                if 0 <= idx < len(r):
                                    new_results.append(r[idx])
                            except ValueError:
                                # Invalid index
                                pass

                    elif isinstance(r, dict):
                        pass

            elif op_type == "filter":
                # Filter the results; only objects that satisfy the condition remain
                for r in results:
                    if isinstance(r, dict) and evaluate_filter_condition(r, value):
                        new_results.append(r)
                    elif isinstance(r, list):
                        # If it's a list, apply the filter to each element
                        for item in r:
                            if isinstance(item, dict) and evaluate_filter_condition(
                                item, value
                            ):
                                new_results.append(item)

            results = new_results

            # If no results remain, break early
            if not results:
                break

        # Recurse with the remaining path parts on the filtered results
        final_results = []
        for res in results:
            final_results.extend(recursive_find(parts[1:], res))

        return final_results

    # Preprocessing the jpath: remove leading "$."
    jpath = jpath.strip()
    if jpath.startswith("$."):
        jpath = jpath[2:]

    # Split by '.' first
    raw_segments = split_path(jpath)

    # Parse each segment into structured operations
    path_parts = [parse_path_segment(s) for s in raw_segments if s]

    # Now recursively find
    return recursive_find(path_parts, obj)


def find_all_by_jsonpaths(jpaths: list, obj: dict) -> list:
    return list(chain.from_iterable([find_all(jpath, obj) for jpath in jpaths]))


def find_all_with_field_value(jpath, field, value, obj):
    # Construct the filter expression
    filter_expr = f"@.{field} == '{value}'"
    cleaned_path = re.sub(r"\[\*]$", "", jpath)
    jsonpath_expr = parse(ensure_root(f"{cleaned_path}[?({filter_expr})]"))
    return [m.value for m in jsonpath_expr.find(obj)]


def find_all_with_filters(jpath, filters, obj):
    # Construct the filter expression
    filter_expr = " & ".join(
        [f"@.{field} == '{value}'" for field, value in filters.items()]
    )
    cleaned_path = re.sub(r"\[\*]$", "", jpath)
    jsonpath_expr = parse(ensure_root(f"{cleaned_path}[?({filter_expr})]"))
    return [m.value for m in jsonpath_expr.find(obj)]


def find_one(jpath, obj, default=None):
    matches = find_all(jpath, obj)

    return matches[0] if len(matches) > 0 else default


def get_dict_of_zones_and_terminals_served_by_hvac_sys(
    rpd: dict,
) -> dict[str, ZonesTerminalsServedByHVACSys]:
    """
    Returns a dictionary of zones and terminal IDs associated with each HVAC system in the RMD.

    Parameters
    ----------
    rpd: dict
    A dictionary representing a RuleModelDescription object as defined by the ASHRAE229 schema

    Returns ------- dict: a dictionary of zones and terminal IDs associated with each HVAC system in the RMD,
    {hvac_system_1.id: {"zone_list": [zone_1.id, zone_2.id, zone_3.id], "terminal_unit_list": [terminal_1.id,
    terminal_2.id, terminal_3.id]}, hvac_system_2.id: {"zone_list": [zone_4.id, zone_9.id, zone_30.id],
    "terminal_unit_list": [terminal_10.id, terminal_20.id, terminal_30.id]}}
    """
    dict_of_zones_and_terminals_served_by_hvac_sys: dict[
        str, ZonesTerminalsServedByHVACSys
    ] = {}

    for zone in find_all(
        "$.ruleset_model_descriptions[*].buildings[*].building_segments[*].zones[*]",
        rpd,
    ):
        zone_id = zone["id"]
        for terminal in find_all("$.terminals[*]", zone):
            terminal_id = terminal["id"]
            hvac_sys_id = terminal.get(
                "served_by_heating_ventilating_air_conditioning_system"
            )
            if hvac_sys_id and isinstance(hvac_sys_id, str):
                if hvac_sys_id not in dict_of_zones_and_terminals_served_by_hvac_sys:
                    dict_of_zones_and_terminals_served_by_hvac_sys[hvac_sys_id] = {
                        "terminal_list": [],
                        "zone_list": [],
                    }

                zone_list = dict_of_zones_and_terminals_served_by_hvac_sys[hvac_sys_id][
                    "zone_list"
                ]
                if zone_id not in zone_list:
                    zone_list.append(zone_id)

                terminal_list = dict_of_zones_and_terminals_served_by_hvac_sys[
                    hvac_sys_id
                ]["terminal_list"]
                if terminal_id not in terminal_list:
                    terminal_list.append(terminal_id)

    return dict_of_zones_and_terminals_served_by_hvac_sys


def get_dict_of_surfaces_with_construction_assigned(rpd: dict) -> dict[str, SurfacesWithConstructionAssigned]:
    dict_of_surfaces_details: dict[
        str, SurfacesWithConstructionAssigned
    ] = {}

    for construction in find_all(
        "$.ruleset_model_descriptions[*].constructions[*]",
        rpd,
    ):
        construction_id = construction["id"]
        if construction_id not in dict_of_surfaces_details:
            dict_of_surfaces_details[construction_id] = {
                "exterior_walls": 0,
                "rooves": 0,
                "below_grade_surfaces": 0,
                "interior_surfaces": 0,
                "primary_layers_length": 0,
                "framing_layers_length": 0,
                "u_factor": None,
                "c_factor": None,
                "f_factor": None,
            }
        dict_of_surfaces_details[construction_id]["primary_layers_length"] = len(construction.get("primary_layers", []))
        dict_of_surfaces_details[construction_id]["framing_layers_length"] = len(construction.get("framing_layers", []))
        dict_of_surfaces_details[construction_id]["u_factor"] = construction.get("u_factor")
        dict_of_surfaces_details[construction_id]["c_factor"] = construction.get("c_factor")
        dict_of_surfaces_details[construction_id]["f_factor"] = construction.get("f_factor")

    for surface in find_all(
        "$.ruleset_model_descriptions[*].buildings[*].building_segments[*].zones[*].surfaces[*]",
        rpd,
    ):
        surface_adjacent_to = surface.get("adjacent_to")
        classification = surface.get("classification")
        tilt = surface.get("tilt", 90)
        construction = surface.get("construction")

        if not construction:
            continue

        # Below grade surface
        if surface_adjacent_to == "GROUND":
            dict_of_surfaces_details[construction][
                "below_grade_surfaces"
            ] += 1
        # Interior surface
        elif surface_adjacent_to == "INTERIOR":
            dict_of_surfaces_details[construction][
                "interior_surfaces"
            ] += 1
        # Exterior wall or roof
        elif surface_adjacent_to == "EXTERIOR":
            if classification == "WALL":
                dict_of_surfaces_details[construction]["exterior_walls"] += 1
            elif classification == "CEILING":
                dict_of_surfaces_details[construction]["rooves"] += 1
            elif classification is None:
                if tilt < 60:
                    dict_of_surfaces_details[construction]["rooves"] += 1
                elif 60 <= tilt < 120:
                    dict_of_surfaces_details[construction]["exterior_walls"] += 1

    return dict_of_surfaces_details


def load_json_file(file_path):
    """Loads JSON data from a file."""
    with open(file_path, "r") as file:
        return json.load(file)


def get_zones_from_json(json_data):
    """Extracts zones from the given JSON data."""
    return find_all(
        "$.ruleset_model_descriptions[0].buildings[0].building_segments[0].zones[*]",
        json_data,
    )


def find_best_match(target, candidates, cutoff=0.4):
    """Finds the best match for a target in a list of candidates."""
    matches = get_close_matches(target, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def compare_values(value, reference_value, absolute_tolerance=None, relative_tolerance=None):
    """Compares a generated value with a reference value based on the tolerance."""
    if isinstance(reference_value, str):
        return value == reference_value

    if isinstance(reference_value, bool):
        return value == reference_value

    if isinstance(reference_value, (int, float)) and absolute_tolerance:
        return math.isclose(value, reference_value, abs_tol=absolute_tolerance)
    elif isinstance(reference_value, (int, float)) and relative_tolerance:
        return math.isclose(value, reference_value, rel_tol=relative_tolerance)

    return False


def compare_azimuth(
    target,
    candidate,
    generated_zone_id,
    reference_zone_id,
    target_value,
    candidate_value,
):
    """Special comparison rule for azimuth attributes."""
    mismatched_wall_origin_adjacent_zone = (
        target.get("adjacent_zone") == generated_zone_id
    ) != (candidate.get("adjacent_zone") == reference_zone_id)
    if (
        not mismatched_wall_origin_adjacent_zone and target_value == candidate_value
    ) or (
        mismatched_wall_origin_adjacent_zone
        and abs(target_value - candidate_value) == 180
    ):
        return 1
    return 0


def compare_fan_power(generated_fans, expected_w_per_flow):
    """Compare the design electric power based on design airflow."""
    warnings = []
    errors = []

    for fan in generated_fans:
        design_flow = fan.get("design_airflow")
        design_power = fan.get("design_electric_power")
        if not design_flow:
            warnings.append(f"Missing design airflow for '{fan['id']}'")
            continue

        if not design_power:
            warnings.append(f"Missing design electric power for '{fan['id']}'")
            continue

        if not compare_values(design_power, expected_w_per_flow * design_flow, abs_tol=1):
            errors.append(
                f"Value mismatch at '{fan['id']}'. Expected: {expected_w_per_flow * design_flow}; got: {design_power}"
            )
    return warnings, errors


def compare_pump_power(pump: dict, expected_w_per_flow: float):
    """Compare the design electric power based on design airflow."""
    warnings = []
    errors = []

    design_flow = pump.get("design_flow")
    design_power = pump.get("design_electric_power")
    if not design_flow:
        warnings.append(f"Missing design flow for '{pump['id']}'")
        return warnings, errors

    if not design_power:
        warnings.append(f"Missing design electric power for '{pump['id']}'")
        return warnings, errors

    if not compare_values(design_power, expected_w_per_flow * design_flow, 1):
        errors.append(
            f"Value mismatch at '{pump['id']}'. Expected: {expected_w_per_flow * design_flow}; got: {design_power}"
        )
    return warnings, errors


def compare_attributes(target, candidate, attr, generated_zone_id=None, reference_zone_id=None):
    """Compares attributes between two objects, with special rules for azimuth and area."""
    if attr not in target:
        return False

    target_value, candidate_value = target.get(attr), candidate.get(attr)
    if attr == "azimuth":
        return compare_azimuth(
            target,
            candidate,
            generated_zone_id,
            reference_zone_id,
            target_value,
            candidate_value,
        )

    elif attr == "area":
        return compare_values(target_value, candidate_value, 0.1)

    elif isinstance(target_value, list):
        candidate_length = len(candidate_value) if candidate_value else 0
        return len(target_value) == candidate_length

    elif isinstance(target_value, (int, float)):
        return compare_values(target_value, candidate_value, relative_tolerance=0.01)

    else:
        return target_value == candidate_value
