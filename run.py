from pathlib import Path

from rpd_tester.perform_comparison import results_data, run_comparison_for_all_tests


CONFIG_DATA = {
    "generation_software_name": "Karpman Consulting RPD Generator",
    "generation_software_version": "1.0.0",
    "modeling_software_name": "eQUEST/DOE2.3",
    "modeling_software_version": "3.65.7175",
    "schema_version": "0.1.4",
    "ruleset_name": "ASHRAE Standard 90.1-2019, Performance Rating Method",
    "ruleset_checking_specification_name": "ASHRAE Standard 90.1-2019, Performance Rating Method",
}

if __name__ == "__main__":
    test_directory = Path(__file__).resolve().parent / "bem_test_files"
    results_data.update(CONFIG_DATA)
    run_comparison_for_all_tests(test_directory)
