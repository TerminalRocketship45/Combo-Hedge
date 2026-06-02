from decimal import Decimal
from optimizer import OptimizationResult
from combos_nba import COMBOS, SCENARIOS
from report import generate_html


def _make_result():
    fill_prices  = {c["id"]: Decimal("0.10") for c in COMBOS}
    contracts    = {c["id"]: Decimal("8.33") for c in COMBOS}
    actual_costs = {c["id"]: Decimal("0.833") for c in COMBOS}
    profits = {}
    for s in SCENARIOS:
        key = f"{s['winner']}_{s['total']}_{s['margin_range']}"
        profits[key] = Decimal("2.50") if "0to4.5" in key else Decimal("-1.00")
    probs = {f"{s['winner']}_{s['total']}_{s['margin_range']}": Decimal("0.083") for s in SCENARIOS}
    return OptimizationResult(
        stakes={c["id"]: Decimal("1.00") for c in COMBOS},
        contracts=contracts,
        actual_costs=actual_costs,
        fill_prices=fill_prices,
        scenario_profits=profits,
        scenario_probs=probs,
        ev=Decimal("0.50"),
        avg_profit=Decimal("1.00"),
        worst_profit=Decimal("-1.00"),
        best_profit=Decimal("5.00"),
        total_deployed=Decimal("9.97"),
    )


def test_generate_html_is_valid_html():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"), fetched_at="19:42:03")
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_generate_html_contains_all_12_combo_ids():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"), fetched_at="19:42:03")
    for combo in COMBOS:
        assert combo["id"] in html, f"Missing combo {combo['id']}"


def test_generate_html_contains_scenario_labels():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"), fetched_at="19:42:03")
    assert "Spurs" in html
    assert "Knicks" in html
    assert "1–4 pts" in html  # "1–4 pts" using en-dash


def test_generate_html_shows_budget():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"), fetched_at="19:42:03")
    assert "10.00" in html


def test_generate_html_shows_deployed():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"), fetched_at="19:42:03")
    assert "9.97" in html


def test_generate_html_shows_ev():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"), fetched_at="19:42:03")
    assert "0.50" in html


def test_generate_html_includes_blowout_warning():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"), fetched_at="19:42:03")
    assert "blowout" in html.lower() or "Blowout" in html
