#!/usr/bin/env python3
"""BRRR deal appraisal calculator — Wales (LTT), Ltd company SPV.

Two modes:
    python3 appraise.py deal.json              # appraise at the stated purchase price
    python3 appraise.py deal.json --max-offer  # also solve for the highest price that still works

Why a script rather than doing this in your head: the model compounds a dozen
inputs through a step-function tax, a rolled-up bridge, two competing loan caps
and a sensitivity grid. Arithmetic done longhand drifts, and a BRRR deal lives
or dies on the last few thousand pounds. Run the script.

Add --json to emit machine-readable output instead of the report.
"""

import argparse
import json
import math
import sys
from copy import deepcopy

# --------------------------------------------------------------------------
# Land Transaction Tax (Wales). Bands are (upper_bound_of_band, rate).
# Verify against gov.wales/land-transaction-tax-rates-and-bands before relying
# on a number — Welsh Government has changed these mid-year before.
# --------------------------------------------------------------------------

LTT_RATES_AS_AT = "2026-09"

HIGHER_RESIDENTIAL = [  # effective 11 December 2024 — separate schedule, starts at £0
    (180_000, 0.050),
    (250_000, 0.085),
    (400_000, 0.100),
    (750_000, 0.125),
    (1_500_000, 0.150),
    (math.inf, 0.170),
]

MAIN_RESIDENTIAL = [  # effective 10 October 2022
    (225_000, 0.000),
    (400_000, 0.060),
    (750_000, 0.075),
    (1_500_000, 0.100),
    (math.inf, 0.120),
]

NON_RESIDENTIAL = [  # effective 22 December 2020
    (225_000, 0.000),
    (250_000, 0.010),
    (1_000_000, 0.050),
    (math.inf, 0.060),
]

HIGHER_RATE_FLOOR = 40_000  # below this consideration, higher rates do not apply


def band_tax(price, bands):
    """Slice the price through the bands, taxing each slice at its own rate."""
    tax = 0.0
    lower = 0.0
    for upper, rate in bands:
        if price <= lower:
            break
        slice_top = min(price, upper)
        tax += (slice_top - lower) * rate
        lower = upper
    return tax


def ltt(price, basis="higher_residential"):
    """Land Transaction Tax due on `price`.

    A company buying a dwelling pays higher residential rates from the first
    pound — there is no nil-rate band. The one relief that matters at the
    bottom of the market: consideration under £40,000 falls outside the higher
    rates entirely, so main rates (0% to £225k) apply instead.
    """
    if basis == "non_residential":
        return band_tax(price, NON_RESIDENTIAL)
    if basis == "main_residential":
        return band_tax(price, MAIN_RESIDENTIAL)
    if price < HIGHER_RATE_FLOOR:
        return band_tax(price, MAIN_RESIDENTIAL)
    return band_tax(price, HIGHER_RESIDENTIAL)


# --------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------

DEFAULTS = {
    "ltt_basis": "higher_residential",
    "refurb": {"budget": 0.0, "contingency_pct": 15.0, "months": 4},
    "purchase_costs": {
        "auction_buyer_premium": 0.0,
        "auction_admin_fee": 0.0,
        "seller_costs_payable_by_buyer": 0.0,
        "solicitor_purchase": 0.0,
        "searches": 0.0,
        "survey": 0.0,
        "ltt_filing": 0.0,
        "other": 0.0,
    },
    "finance": {
        "method": "cash",
        "bridge_ltv_pct": 70.0,
        "bridge_monthly_rate_pct": 0.95,
        "bridge_arrangement_fee_pct": 2.0,
        "bridge_exit_fee_pct": 0.0,
        "bridge_legal_and_valuation": 0.0,
        "broker_fee": 0.0,
        "roll_up_interest": True,
    },
    "refinance": {
        "ltv_pct": 75.0,
        "rate_pct": 5.4,
        "product_fee_pct": 3.0,
        "product_fee_added_to_loan": True,
        "icr_pct": 125.0,
        "stress_rate_pct": 5.5,
        "legal_and_valuation": 0.0,
        "broker_fee": 0.0,
    },
    "holding_costs_monthly": {"council_tax": 0.0, "insurance": 0.0, "utilities": 0.0, "other": 0.0},
    "operating_costs": {
        "management_pct": 10.0,
        "maintenance_pct": 5.0,
        "voids_pct": 5.0,
        "insurance_annual": 0.0,
        "ground_rent_and_service_charge_annual": 0.0,
        "other_annual": 0.0,
    },
    "criteria": {
        "max_money_left_in": 0.0,
        "min_monthly_cashflow": 200.0,
        "min_roi_pct": 15.0,
        "min_yield_on_value_pct": 7.0,
    },
}


def merge(base, override):
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_deal(path):
    with open(path) as handle:
        raw = json.load(handle)
    deal = merge(DEFAULTS, raw)
    for required in ("purchase_price", "post_refurb_value", "monthly_rent"):
        if raw.get(required) is None:
            sys.exit(
                f"Missing required input '{required}'. All three of purchase_price, "
                "post_refurb_value and monthly_rent must be evidenced before the "
                "numbers mean anything — see references/valuation-evidence.md."
            )
    return deal


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------


def appraise(deal, price=None):
    """Run the full BRRR model. `price` overrides purchase_price for solving."""
    price = deal["purchase_price"] if price is None else price
    value = deal["post_refurb_value"]
    rent = deal["monthly_rent"]

    fin = deal["finance"]
    refi = deal["refinance"]
    rfb = deal["refurb"]
    months = rfb["months"]

    # --- acquisition costs -------------------------------------------------
    tax = ltt(price, deal["ltt_basis"])
    pc = deal["purchase_costs"]
    transaction_fees = sum(pc.values())

    refurb_budget = rfb["budget"]
    contingency = refurb_budget * rfb["contingency_pct"] / 100.0
    refurb_total = refurb_budget + contingency

    # --- bridging ----------------------------------------------------------
    if fin["method"] == "bridging":
        bridge_loan = price * fin["bridge_ltv_pct"] / 100.0
        arrangement_fee = bridge_loan * fin["bridge_arrangement_fee_pct"] / 100.0
        bridge_interest = bridge_loan * fin["bridge_monthly_rate_pct"] / 100.0 * months
        exit_fee = bridge_loan * fin["bridge_exit_fee_pct"] / 100.0
        if fin["roll_up_interest"]:
            interest_paid_in_cash = 0.0
            redemption = bridge_loan + bridge_interest + exit_fee
        else:
            interest_paid_in_cash = bridge_interest
            redemption = bridge_loan + exit_fee
    else:
        bridge_loan = arrangement_fee = bridge_interest = exit_fee = 0.0
        interest_paid_in_cash = redemption = 0.0

    finance_fees = arrangement_fee + fin["bridge_legal_and_valuation"] + fin["broker_fee"]

    holding = sum(deal["holding_costs_monthly"].values()) * months

    cash_in = (
        price
        + tax
        + transaction_fees
        + refurb_total
        + finance_fees
        + interest_paid_in_cash
        + holding
        - bridge_loan
    )

    # --- refinance: two competing caps, the lower one binds -----------------
    ltv_cap = value * refi["ltv_pct"] / 100.0
    stress_annual_rate = refi["icr_pct"] / 100.0 * refi["stress_rate_pct"] / 100.0
    icr_cap = (rent * 12.0) / stress_annual_rate if stress_annual_rate > 0 else math.inf
    refi_loan = min(ltv_cap, icr_cap)
    binding_cap = "LTV" if ltv_cap <= icr_cap else "rental stress test (ICR)"

    product_fee = refi_loan * refi["product_fee_pct"] / 100.0
    refi_cash_costs = refi["legal_and_valuation"] + refi["broker_fee"]
    if refi["product_fee_added_to_loan"]:
        net_release = refi_loan - product_fee - redemption - refi_cash_costs
        mortgage_balance = refi_loan
    else:
        net_release = refi_loan - redemption - refi_cash_costs - product_fee
        mortgage_balance = refi_loan

    money_left_in = cash_in - net_release

    # --- post-refinance operating position ---------------------------------
    op = deal["operating_costs"]
    mortgage_monthly = mortgage_balance * refi["rate_pct"] / 100.0 / 12.0
    management = rent * op["management_pct"] / 100.0
    maintenance = rent * op["maintenance_pct"] / 100.0
    voids = rent * op["voids_pct"] / 100.0
    fixed_monthly = (
        op["insurance_annual"]
        + op["ground_rent_and_service_charge_annual"]
        + op["other_annual"]
    ) / 12.0
    monthly_cashflow = rent - mortgage_monthly - management - maintenance - voids - fixed_monthly
    annual_cashflow = monthly_cashflow * 12.0

    if money_left_in <= 0:
        roi = math.inf
    elif annual_cashflow <= 0:
        roi = annual_cashflow / money_left_in * 100.0
    else:
        roi = annual_cashflow / money_left_in * 100.0

    equity = value - mortgage_balance
    total_project_cost = (
        price + tax + transaction_fees + refurb_total + finance_fees + bridge_interest
        + exit_fee + holding + product_fee + refi_cash_costs
    )
    profit_on_paper = value - total_project_cost
    yield_on_value = rent * 12.0 / value * 100.0 if value else 0.0

    return {
        "purchase_price": price,
        "ltt": tax,
        "transaction_fees": transaction_fees,
        "refurb_budget": refurb_budget,
        "refurb_contingency": contingency,
        "refurb_total": refurb_total,
        "bridge_loan": bridge_loan,
        "bridge_arrangement_fee": arrangement_fee,
        "bridge_interest": bridge_interest,
        "bridge_exit_fee": exit_fee,
        "finance_fees": finance_fees,
        "interest_paid_in_cash": interest_paid_in_cash,
        "holding_costs": holding,
        "cash_in": cash_in,
        "ltv_cap": ltv_cap,
        "icr_cap": icr_cap,
        "refi_loan": refi_loan,
        "binding_cap": binding_cap,
        "product_fee": product_fee,
        "refi_cash_costs": refi_cash_costs,
        "redemption": redemption,
        "net_release": net_release,
        "money_left_in": money_left_in,
        "mortgage_monthly": mortgage_monthly,
        "management": management,
        "maintenance": maintenance,
        "voids": voids,
        "fixed_monthly": fixed_monthly,
        "monthly_cashflow": monthly_cashflow,
        "annual_cashflow": annual_cashflow,
        "roi": roi,
        "equity": equity,
        "total_project_cost": total_project_cost,
        "profit_on_paper": profit_on_paper,
        "yield_on_value": yield_on_value,
    }


def test_criteria(result, criteria):
    """Every test the deal has to pass, with the numbers that decided it."""
    return [
        (
            "Money left in",
            result["money_left_in"] <= criteria["max_money_left_in"],
            f"£{result['money_left_in']:,.0f} vs limit £{criteria['max_money_left_in']:,.0f}",
        ),
        (
            "Monthly cashflow",
            result["monthly_cashflow"] >= criteria["min_monthly_cashflow"],
            f"£{result['monthly_cashflow']:,.0f} vs minimum £{criteria['min_monthly_cashflow']:,.0f}",
        ),
        (
            "Return on capital left in",
            result["roi"] >= criteria["min_roi_pct"],
            ("all capital recycled" if math.isinf(result["roi"])
             else f"{result['roi']:.1f}% vs minimum {criteria['min_roi_pct']:.1f}%"),
        ),
        (
            "Yield on end value",
            result["yield_on_value"] >= criteria["min_yield_on_value_pct"],
            f"{result['yield_on_value']:.1f}% vs minimum {criteria['min_yield_on_value_pct']:.1f}%",
        ),
    ]


def solve_max_offer(deal, criteria_subset=None):
    """Highest purchase price at which the deal still passes.

    Everything that matters gets worse as the price rises and nothing gets
    better, so the pass/fail boundary is a single crossing point and bisection
    finds it exactly. Solved to the nearest £100 because no one offers £117,346.
    """
    crit = deal["criteria"]

    def passes(price):
        result = appraise(deal, price)
        tests = test_criteria(result, crit)
        if criteria_subset:
            tests = [t for t in tests if t[0] in criteria_subset]
        return all(ok for _, ok, _ in tests)

    lo, hi = 0.0, max(deal["post_refurb_value"], deal["purchase_price"]) * 1.5
    if not passes(lo):
        return None  # fails even at a £0 purchase price — the deal is structurally dead
    if passes(hi):
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        if passes(mid):
            lo = mid
        else:
            hi = mid
    return math.floor(lo / 100.0) * 100.0


def sensitivities(deal):
    """BRRR deals die at the valuation, not at the offer. Model the three ways."""
    out = {}

    down_val = deepcopy(deal)
    down_val["post_refurb_value"] = deal["post_refurb_value"] * 0.90
    out["End value down 10%"] = appraise(down_val)

    overrun = deepcopy(deal)
    overrun["refurb"]["budget"] = deal["refurb"]["budget"] * 1.25
    overrun["refurb"]["months"] = deal["refurb"]["months"] + 2
    out["Refurb 25% over, 2 months late"] = appraise(overrun)

    rates = deepcopy(deal)
    rates["refinance"]["rate_pct"] = deal["refinance"]["rate_pct"] + 1.0
    rates["refinance"]["stress_rate_pct"] = max(
        deal["refinance"]["stress_rate_pct"], deal["refinance"]["rate_pct"] + 3.0
    )
    out["Refinance rate up 1%"] = appraise(rates)

    soft_rent = deepcopy(deal)
    soft_rent["monthly_rent"] = deal["monthly_rent"] * 0.90
    out["Rent 10% below expectation"] = appraise(soft_rent)

    return out


def ltv_tradeoff(deal, price=None, ltvs=(60, 65, 70, 75, 80)):
    """The real BRRR lever, once the price is agreed.

    Borrowing less leaves more of your cash stranded but costs less every month.
    There is no universally right answer — it depends on whether you are short of
    capital or short of income — so put the trade-off in front of the buyer
    rather than assuming maximum leverage is the goal.
    """
    rows = []
    for ltv in ltvs:
        variant = deepcopy(deal)
        variant["refinance"]["ltv_pct"] = ltv
        result = appraise(variant, price)
        rows.append((ltv, result))
    return rows


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def money(x):
    return f"£{x:,.0f}"


def report(deal, result, max_offer=None, show_sensitivity=True):
    lines = []
    add = lines.append
    crit = deal["criteria"]

    add(f"# Deal appraisal — {deal.get('address', 'unnamed property')}")
    add("")
    add(f"Appraised at a purchase price of {money(result['purchase_price'])}.")
    add(f"LTT basis: {deal['ltt_basis'].replace('_', ' ')} (rates as at {LTT_RATES_AS_AT}).")
    add("")

    add("## Money in")
    add("")
    add("| Item | Amount |")
    add("| --- | ---: |")
    add(f"| Purchase price | {money(result['purchase_price'])} |")
    add(f"| Land Transaction Tax | {money(result['ltt'])} |")
    add(f"| Legal, survey, auction and transaction fees | {money(result['transaction_fees'])} |")
    add(f"| Refurb budget | {money(result['refurb_budget'])} |")
    add(f"| Refurb contingency | {money(result['refurb_contingency'])} |")
    add(f"| Finance arrangement, valuation and broker fees | {money(result['finance_fees'])} |")
    if result["interest_paid_in_cash"]:
        add(f"| Bridge interest paid monthly | {money(result['interest_paid_in_cash'])} |")
    add(f"| Holding costs during works | {money(result['holding_costs'])} |")
    if result["bridge_loan"]:
        add(f"| Less bridging advance | ({money(result['bridge_loan'])}) |")
    add(f"| **Cash required** | **{money(result['cash_in'])}** |")
    add("")

    add("## Refinance")
    add("")
    add(f"- 75%-style LTV cap on an end value of {money(deal['post_refurb_value'])}: "
        f"{money(result['ltv_cap'])}")
    add(f"- Rental stress cap ({deal['refinance']['icr_pct']:.0f}% cover at "
        f"{deal['refinance']['stress_rate_pct']:.2f}%): {money(result['icr_cap'])}")
    add(f"- **Loan available: {money(result['refi_loan'])}** — limited by the "
        f"{result['binding_cap']}")
    if result["redemption"]:
        add(f"- Bridge redemption (capital, rolled interest and exit fee): "
            f"{money(result['redemption'])}")
    add(f"- Product fee: {money(result['product_fee'])}; legal, valuation and broker: "
        f"{money(result['refi_cash_costs'])}")
    add(f"- **Net cash released: {money(result['net_release'])}**")
    add("")
    if result["money_left_in"] <= 0:
        add(f"**Money left in the deal: {money(result['money_left_in'])}** — the refinance "
            f"recycles all of your capital and returns {money(-result['money_left_in'])} on top.")
    else:
        add(f"**Money left in the deal: {money(result['money_left_in'])}**")
    add("")

    add("## Once let and refinanced")
    add("")
    add("| Item | Monthly |")
    add("| --- | ---: |")
    add(f"| Rent | {money(deal['monthly_rent'])} |")
    add(f"| Mortgage interest | ({money(result['mortgage_monthly'])}) |")
    add(f"| Letting management | ({money(result['management'])}) |")
    add(f"| Maintenance reserve | ({money(result['maintenance'])}) |")
    add(f"| Voids reserve | ({money(result['voids'])}) |")
    add(f"| Insurance and fixed charges | ({money(result['fixed_monthly'])}) |")
    add(f"| **Net cashflow** | **{money(result['monthly_cashflow'])}** |")
    add("")
    roi_text = ("infinite — no capital left in" if math.isinf(result["roi"])
                else f"{result['roi']:.1f}%")
    add(f"Annual cashflow {money(result['annual_cashflow'])}. Return on capital left in: {roi_text}.")
    add(f"Equity created: {money(result['equity'])} "
        f"(end value {money(deal['post_refurb_value'])} less debt {money(result['refi_loan'])}).")
    add(f"Total project cost {money(result['total_project_cost'])} against an end value of "
        f"{money(deal['post_refurb_value'])} — {money(result['profit_on_paper'])} of margin.")
    add("")

    add("## Against your criteria")
    add("")
    add("| Test | Result | Verdict |")
    add("| --- | --- | --- |")
    tests = test_criteria(result, crit)
    for name, ok, detail in tests:
        add(f"| {name} | {detail} | {'PASS' if ok else 'FAIL'} |")
    add("")

    passed = sum(1 for _, ok, _ in tests if ok)
    if passed == len(tests):
        add(f"**Verdict: the deal works at {money(result['purchase_price'])}.**")
    elif passed == 0:
        add(f"**Verdict: the deal does not work at {money(result['purchase_price'])}** — it "
            "fails every test.")
    else:
        failed = ", ".join(name.lower() for name, ok, _ in tests if not ok)
        add(f"**Verdict: the deal does not work at {money(result['purchase_price'])}** — it "
            f"fails on {failed}.")
    add("")

    if max_offer is not None:
        add("## Maximum offer")
        add("")

        ceilings = []
        for label in ("Money left in", "Monthly cashflow", "Return on capital left in",
                      "Yield on end value"):
            ceilings.append((label, solve_max_offer(deal, criteria_subset={label})))

        if max_offer is False:
            blocked = [label for label, ceiling in ceilings if ceiling is None]
            add("**There is no purchase price at which this deal meets your criteria — not "
                "even at zero.**")
            add("")
            add(f"These tests fail at any price: {', '.join(blocked).lower()}.")
            add("")
            add("That is not a quirk of the model. Once you refinance, your debt is set by "
                "the end value and the rent, not by what you paid — so the mortgage payment, "
                "the cashflow and the yield are all fixed before you make an offer. Paying "
                "less improves how much capital you get back; it does not improve the monthly "
                "position at all. A deal that fails on cashflow or yield can only be fixed by "
                "a higher rent, a cheaper refinance, or a different property.")
        else:
            add(f"**Offer no more than {money(max_offer)}** to meet every criterion.")
            add("")
            add("| Criterion | Price ceiling |")
            add("| --- | ---: |")
            for label, ceiling in ceilings:
                if ceiling is None:
                    text = "fails at any price"
                elif ceiling >= deal["post_refurb_value"] * 1.49:
                    text = "not price-sensitive"
                else:
                    text = money(ceiling)
                add(f"| {label} | {text} |")
            add("")
            binding = min(
                ((label, c) for label, c in ceilings if c is not None),
                key=lambda item: item[1],
            )[0]
            add(f"The binding constraint is **{binding.lower()}** — that is the test which "
                "stops you bidding higher, and the one to attack if you want the ceiling to "
                "move. Money left in is capital-efficiency limited, so a stronger end value "
                "or a cheaper refurb raises it. Cashflow and yield barely move with price at "
                "all, because the debt you carry after refinancing is set by the end value "
                "and the rent, not by what you paid.")
        add("")

    add("## The leverage trade-off")
    add("")
    add("Borrowing less at refinance strands more of your cash but buys you monthly "
        "headroom. At this price:")
    add("")
    add("| Refinance LTV | Loan | Money left in | Monthly cashflow | Return on capital |")
    add("| ---: | ---: | ---: | ---: | ---: |")
    for ltv, row in ltv_tradeoff(deal, result["purchase_price"]):
        roi_cell = ("infinite" if math.isinf(row["roi"]) else f"{row['roi']:.1f}%")
        marker = " *" if abs(ltv - deal["refinance"]["ltv_pct"]) < 0.01 else ""
        add(f"| {ltv:.0f}%{marker} | {money(row['refi_loan'])} | "
            f"{money(row['money_left_in'])} | {money(row['monthly_cashflow'])} | {roi_cell} |")
    add("")
    add("(* the LTV you asked me to model.) Maximum leverage is not automatically the "
        "right answer — it is the right answer only when capital is your scarcest "
        "resource. If the monthly figure at your chosen LTV is uncomfortably thin, the "
        "honest conclusion is usually that this deal needs more of your money in it, "
        "not that it needs a lower offer.")
    add("")

    if show_sensitivity:
        add("## What breaks it")
        add("")
        add("| Scenario | Money left in | Monthly cashflow |")
        add("| --- | ---: | ---: |")
        add(f"| As modelled | {money(result['money_left_in'])} | {money(result['monthly_cashflow'])} |")
        for label, scenario in sensitivities(deal).items():
            add(f"| {label} | {money(scenario['money_left_in'])} | "
                f"{money(scenario['monthly_cashflow'])} |")
        add("")
        add("A down-valuation at refinance is the single most common way a BRRR deal fails. "
            "If the 10% row leaves more capital stranded than you can afford, the deal has no "
            "margin for error regardless of what the base case says.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deal", help="path to the deal JSON file")
    parser.add_argument("--max-offer", action="store_true",
                        help="also solve for the highest price that meets every criterion")
    parser.add_argument("--no-sensitivity", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit raw numbers instead of a report")
    args = parser.parse_args()

    deal = load_deal(args.deal)
    result = appraise(deal)

    if args.json:
        payload = {"appraisal": result}
        if args.max_offer:
            solved = solve_max_offer(deal)
            payload["max_offer"] = solved
        print(json.dumps(payload, indent=2, default=lambda v: None if v == math.inf else v))
        return

    max_offer = None
    if args.max_offer:
        solved = solve_max_offer(deal)
        max_offer = False if solved is None else solved

    print(report(deal, result, max_offer=max_offer, show_sensitivity=not args.no_sensitivity))


if __name__ == "__main__":
    main()
