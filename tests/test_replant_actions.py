"""Tests for replant action registration (Phase 2: species-switching transitions).

All tests use the synthetic fixture — no annex bundle required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fresh_fuchs.instance.replant import (
    REPLANT_SUFFIX,
    add_replant_actions,
    add_replant_salvage_actions,
    replant_au_id,
)
from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.instance.synthetic import (
    build_synthetic_areas,
    build_synthetic_yields,
    synthetic_instance_config,
)
from fresh_fuchs.instance.woodstock import (
    bootstrap_model,
    prepare_optimization,
    write_woodstock_files,
)

# ---------------------------------------------------------------------------
# replant_au_id
# ---------------------------------------------------------------------------


class TestReplantAuId:
    def test_spruce(self) -> None:
        assert replant_au_id(1001, SpeciesClass.SPRUCE) == "1001-SX"

    def test_pine(self) -> None:
        assert replant_au_id(1001, SpeciesClass.LODGEPOLE_PINE) == "1001-PL"

    def test_fir(self) -> None:
        assert replant_au_id(1001, SpeciesClass.DOUGLAS_FIR) == "1001-FD"

    def test_other(self) -> None:
        assert replant_au_id(1001, SpeciesClass.OTHER) == "1001-OT"

    def test_string_au(self) -> None:
        assert replant_au_id("204", SpeciesClass.SPRUCE) == "204-SX"

    def test_suffix_roundtrip(self) -> None:
        for sp, suffix in REPLANT_SUFFIX.items():
            rau = replant_au_id(42, sp)
            assert rau == f"42{suffix}"


# ---------------------------------------------------------------------------
# add_replant_actions
# ---------------------------------------------------------------------------


def _build_model_with_replant(
    tmp_path: Path,
    *,
    target_species: tuple[SpeciesClass, ...] = (
        SpeciesClass.SPRUCE,
        SpeciesClass.LODGEPOLE_PINE,
    ),
):
    """Helper: build a synthetic model with replant actions registered."""
    config = synthetic_instance_config(tmp_path, horizon=2)
    write_woodstock_files(
        areas=build_synthetic_areas(),
        yields=build_synthetic_yields(),
        config=config,
    )
    model = bootstrap_model(config)
    prepare_optimization(
        model,
        max_initial_age=300,
        config=config,
        replant_species=target_species,
    )
    return model


class TestAddReplantActions:
    def test_registers_harvest_sx(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        assert "harvest_SX" in model.actions
        assert model.actions["harvest_SX"].is_harvest

    def test_registers_harvest_pl(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        assert "harvest_PL" in model.actions
        assert model.actions["harvest_PL"].is_harvest

    def test_does_not_register_fd_when_not_requested(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(
            tmp_path, target_species=(SpeciesClass.SPRUCE,)
        )
        assert "harvest_SX" in model.actions
        assert "harvest_PL" not in model.actions
        assert "harvest_FD" not in model.actions

    def test_original_harvest_unchanged(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        assert "harvest" in model.actions
        assert model.actions["harvest"].is_harvest

    def test_all_action_keys(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        expected = {"null", "harvest", "harvest_SX", "harvest_PL"}
        assert set(model.actions.keys()) == expected

    def test_idempotent(self, tmp_path: Path) -> None:
        config = synthetic_instance_config(tmp_path, horizon=2)
        write_woodstock_files(
            areas=build_synthetic_areas(),
            yields=build_synthetic_yields(),
            config=config,
        )
        model = bootstrap_model(config)
        prepare_optimization(
            model,
            max_initial_age=300,
            config=config,
            replant_species=(SpeciesClass.SPRUCE,),
        )
        # Call again — should not duplicate.
        add_replant_actions(
            model,
            target_species=(SpeciesClass.SPRUCE,),
            min_harvest_age=60,
            max_harvest_age=300,
        )
        assert list(model.actions.keys()).count("harvest_SX") == 1


class TestReplantOperability:
    def test_operable_on_managed_stands(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        # AU1 managed, age 75 is harvestable (60 <= 75 <= 300).
        operable = model.operable_area("harvest_SX", period=1)
        assert operable > 0

    def test_operable_area_matches_harvest(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        # Replant actions should be operable on the same area as harvest.
        harvest_area = model.operable_area("harvest", period=1)
        sx_area = model.operable_area("harvest_SX", period=1)
        pl_area = model.operable_area("harvest_PL", period=1)
        assert sx_area == pytest.approx(harvest_area)
        assert pl_area == pytest.approx(harvest_area)


class TestReplantTransitions:
    def test_transition_target_has_species_suffix(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        # Check the transition tuple for harvest_SX on any managed dtype.
        for dtk, dt in model.dtypes.items():
            if dtk[1] != "managed":
                continue
            transitions = dt.transitions.get(("harvest_SX", -1))
            assert transitions is not None
            assert len(transitions) == 1
            tmask, tprop, tyield, tage, tlock, treplace, tappend = transitions[0]
            # Target AU should contain the species suffix.
            assert "SX" in str(tmask[2])
            # Source AU code should be preserved in the suffix.
            assert str(dtk[2]) in str(tmask[2])
            break

    def test_transition_resets_age_to_zero(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        dtk = list(model.dtypes.keys())[0]
        dt = model.dtypes[dtk]
        transitions = dt.transitions.get(("harvest_SX", -1))
        assert transitions is not None
        tage = transitions[0][3]
        assert tage == 0

    def test_transition_is_100_percent(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        dtk = list(model.dtypes.keys())[0]
        dt = model.dtypes[dtk]
        transitions = dt.transitions.get(("harvest_SX", -1))
        assert transitions is not None
        tprop = transitions[0][1]
        assert tprop == 1.0


class TestReplantApply:
    def test_apply_transitions_to_replant_au(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        # Find a managed, harvestable dtype.
        target_dtk = None
        for dtk, dt in model.dtypes.items():
            if dtk[1] == "managed" and dt.area(0) > 0:
                target_dtk = dtk
                break
        assert target_dtk is not None

        dt = model.dtypes[target_dtk]
        ages = dt.operable_ages("harvest_SX", period=1)
        assert ages is not None and len(ages) > 0

        age = ages[-1]
        area = dt.area(1, age)
        assert area > 0

        # Apply the action.
        errorcode, missing, target_dt = model.apply_action(
            target_dtk, "harvest_SX", 1, age, area
        )
        assert errorcode == 0
        assert target_dt is not None
        assert len(target_dt) == 1

        new_dtk, tprop, target_age = target_dt[0]
        # Target AU should have the species suffix.
        au_val = new_dtk[2]
        assert "SX" in str(au_val)
        assert target_age == 0

    def test_apply_pl_produces_pl_au(self, tmp_path: Path) -> None:
        model = _build_model_with_replant(tmp_path)
        target_dtk = None
        for dtk, dt in model.dtypes.items():
            if dtk[1] == "managed" and dt.area(0) > 0:
                target_dtk = dtk
                break
        assert target_dtk is not None

        dt = model.dtypes[target_dtk]
        ages = dt.operable_ages("harvest_PL", period=1)
        assert ages is not None and len(ages) > 0

        age = ages[-1]
        area = dt.area(1, age)
        errorcode, _, target_dt = model.apply_action(
            target_dtk, "harvest_PL", 1, age, area
        )
        assert errorcode == 0
        new_dtk = target_dt[0][0]
        assert "PL" in str(new_dtk[2])


# ---------------------------------------------------------------------------
# add_replant_salvage_actions
# ---------------------------------------------------------------------------


class TestReplantSalvageActions:
    def test_registers_salvage_sx(self, tmp_path: Path) -> None:
        config = synthetic_instance_config(tmp_path, horizon=2)
        write_woodstock_files(
            areas=build_synthetic_areas(),
            yields=build_synthetic_yields(),
            config=config,
        )
        model = bootstrap_model(config)
        prepare_optimization(model, max_initial_age=300, config=config)

        # Add base salvage first.
        from fresh_fuchs.scenario.fire_lp import add_salvage_action

        add_salvage_action(model)

        # Now add replant salvage actions.
        add_replant_salvage_actions(
            model,
            target_species=(SpeciesClass.SPRUCE,),
            min_salvage_age=60,
            max_salvage_age=300,
        )
        assert "salvage_SX" in model.actions

    def test_salvage_operable(self, tmp_path: Path) -> None:
        config = synthetic_instance_config(tmp_path, horizon=2)
        write_woodstock_files(
            areas=build_synthetic_areas(),
            yields=build_synthetic_yields(),
            config=config,
        )
        model = bootstrap_model(config)
        prepare_optimization(model, max_initial_age=300, config=config)

        from fresh_fuchs.scenario.fire_lp import add_salvage_action

        add_salvage_action(model)
        add_replant_salvage_actions(
            model,
            target_species=(SpeciesClass.SPRUCE,),
            min_salvage_age=60,
            max_salvage_age=300,
        )

        operable = model.operable_area("salvage_SX", period=1)
        assert operable > 0


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_no_replant_preserves_original_actions(self, tmp_path: Path) -> None:
        config = synthetic_instance_config(tmp_path, horizon=2)
        write_woodstock_files(
            areas=build_synthetic_areas(),
            yields=build_synthetic_yields(),
            config=config,
        )
        model = bootstrap_model(config)
        prepare_optimization(model, max_initial_age=300, config=config)
        # Without replant_species, only null + harvest.
        assert set(model.actions.keys()) == {"null", "harvest"}

    def test_no_replant_area_conserved(self, tmp_path: Path) -> None:
        config = synthetic_instance_config(tmp_path, horizon=2)
        write_woodstock_files(
            areas=build_synthetic_areas(),
            yields=build_synthetic_yields(),
            config=config,
        )
        model = bootstrap_model(config)
        prepare_optimization(model, max_initial_age=300, config=config)
        total_area = build_synthetic_areas()["area_ha"].sum()
        assert model.inventory(period=0) == pytest.approx(total_area, abs=0.01)
