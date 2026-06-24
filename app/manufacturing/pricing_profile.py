from app.schemas.analysis_schema import MachiningProfile, ManufacturingProfile, PieceSize


MACHINE_BY_PROFILE = {
    "bench_milling": "bench_3_axis",
    "vertical_milling": "vertical_3_axis",
    "portal_milling": "gantry_3_axis",
    "lathe_candidate": "cnc_lathe",
    "mold_base_candidate": "mold_base_machining_center",
    "complex_3_axis_milling": "high_precision_3_axis",
    "precision_fixture_required": "fixture_assisted_3_axis",
    "engineering_review_required": "engineering_review",
}


def get_pricing_profile(
    piece_size: PieceSize,
    machining_profile: MachiningProfile,
) -> ManufacturingProfile:
    if machining_profile == "engineering_review_required":
        return ManufacturingProfile(
            piece_size=piece_size,
            machining_profile=machining_profile,
            estimated_machine_type=MACHINE_BY_PROFILE[machining_profile],
            setup_hours=1.5,
            machine_rate_brl_hour=220,
        )

    if machining_profile in {"complex_3_axis_milling", "precision_fixture_required"}:
        return ManufacturingProfile(
            piece_size=piece_size,
            machining_profile=machining_profile,
            estimated_machine_type=MACHINE_BY_PROFILE[machining_profile],
            setup_hours=1.0,
            machine_rate_brl_hour=190,
        )

    if piece_size == "small":
        return ManufacturingProfile(
            piece_size="small",
            machining_profile=machining_profile,
            estimated_machine_type=MACHINE_BY_PROFILE[machining_profile],
            setup_hours=0.5,
            machine_rate_brl_hour=150,
        )

    return ManufacturingProfile(
        piece_size="large",
        machining_profile=machining_profile,
        estimated_machine_type=MACHINE_BY_PROFILE[machining_profile],
        setup_hours=1.0,
        machine_rate_brl_hour=200,
    )
