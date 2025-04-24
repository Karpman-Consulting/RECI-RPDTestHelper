from pathlib import Path

from rpd_tester.perform_comparison import results_data, run_comparison_for_all_tests

# ---------- SET THE VALUES FOR ALL CONFIGURATION VARIABLES ----------
GENERATION_SOFTWARE_NAME = ""
GENERATION_SOFTWARE_VERSION = ""
MODELING_SOFTWARE_NAME = ""
MODELING_SOFTWARE_VERSION = ""
SCHEMA_VERSION = "0.0.36"
RULESET_NAME = "ASHRAE Standard 90.1-2019, Performance Rating Method"
RULESET_CHECKING_SPECIFICATION_NAME = "ASHRAE Standard 90.1-2019, Performance Rating Method"
# --------------------------------------------------------------------
# SET THE VALUES FOR ALL CONFIGURATION VARIABLES
GENERATION_SOFTWARE_NAME = "Karpman Consulting RPD Generator"
GENERATION_SOFTWARE_VERSION = "1.0.0"
MODELING_SOFTWARE_NAME = "eQUEST/DOE2.3"
MODELING_SOFTWARE_VERSION = "3.65.7175"
SCHEMA_VERSION = "0.0.36"
RULESET_NAME = "ASHRAE Standard 90.1-2019, Performance Rating Method"
RULESET_CHECKING_SPECIFICATION_NAME = "ASHRAE Standard 90.1-2019, Performance Rating Method"

if __name__ == "__main__":
    config_vars = [
        GENERATION_SOFTWARE_NAME,
        GENERATION_SOFTWARE_VERSION,
        MODELING_SOFTWARE_NAME,
        MODELING_SOFTWARE_VERSION,
        SCHEMA_VERSION,
        RULESET_NAME,
        RULESET_CHECKING_SPECIFICATION_NAME,
    ]
    if any(not var for var in config_vars):
        raise ValueError("All configuration variables must be set in 'run.py'.")

    CONFIG_DATA = {
        "generation_software_name": GENERATION_SOFTWARE_NAME,
        "generation_software_version": GENERATION_SOFTWARE_VERSION,
        "modeling_software_name": MODELING_SOFTWARE_NAME,
        "modeling_software_version": MODELING_SOFTWARE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "ruleset_name": RULESET_NAME,
        "ruleset_checking_specification_name": RULESET_CHECKING_SPECIFICATION_NAME,
    }
    test_directory = Path(__file__).resolve().parent / "bem_test_files"
    results_data.update(CONFIG_DATA)
    run_comparison_for_all_tests(test_directory)
