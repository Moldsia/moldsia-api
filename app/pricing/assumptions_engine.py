from app.schemas.mold_quote_schema import MoldTechnicalInput


def build_mold_pricing_assumptions(technical_input: MoldTechnicalInput) -> list[str]:
    assumptions = [
        "mold_size_estimated_from_part_envelope_shrinkage_cavity_layout_and_steel_margins",
        "mold_base_selected_from_configurable_standard_size_table",
        "plate_stack_height_estimated_from_part_depth_ejection_cooling_and_mold_type",
        "components_generated_from_standard_injection_moldbase_structure",
        "mrr_estimated_by_component_material_and_operation_from_editable_library",
        f"mrr_config_version:{technical_input.mrr_config_version}",
        "hardware_cost_table_used",
        "single_tryout_cycle_assumed",
        "edm_estimated_by_complexity",
    ]
    if technical_input.injection_type == "hot_runner":
        assumptions.append("hot_runner_cost_table_used")
    if technical_input.surface_treatment != "NOT_DEFINED":
        assumptions.append("surface_treatment_estimated_by_molding_set_weight")
    if technical_input.main_finish in {"MIRROR_POLISH", "HIGH_GLOSS", "TEXTURED", "MIXED"}:
        assumptions.append("finish_complexity_added_from_technical_form")
    if technical_input.extras.moldflow:
        assumptions.append("moldflow_hours_added_from_technical_form")
    if technical_input.cad_movement_warning:
        assumptions.append("cad_movement_warning_requires_engineering_review")
    return assumptions


