from rpd_tester.utils import *


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

        if not compare_values(design_power, expected_w_per_flow * design_flow, 1):
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
