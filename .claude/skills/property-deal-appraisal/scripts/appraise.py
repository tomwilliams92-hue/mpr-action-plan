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

# Defaults are the mid-points of the ranges in references/cost-benchmarks.md,
# not zero. A cost left out of the input file should make the appraisal
# realistic, not optimistic — an omitted solicitor fee silently costing nothing
# flatters every deal that passes through.
#
# The two exceptions are the auction fees, which stay at zero because they
# depend entirely on which kind of auction it is, and guessing wrong in either
# direction is worse than a visible zero the buyer has to fill in.
DEFAULTS = {
    "ltt_basis": "higher_residential",
    "refurb": {"budget": 0.0, "contingency_pct": 15.0, "months": 5},
    "purchase_costs": {
        "auction_buyer_premium": 0.0,
        "auction_admin_fee": 0.0,
        "seller_costs_payable_by_buyer": 0.0,
        "solicitor_purchase": 1_900.0,
        "searches": 420.0,
        "survey": 900.0,
        "ltt_filing": 150.0,
        "other": 95.0,
    },
    "finance": {
        "method": "bridging",
        "bridge_ltv_pct": 70.0,
        "bridge_monthly_rate_pct": 0.95,
        "bridge_arrangement_fee_pct": 2.0,
        "bridge_exit_fee_pct": 0.0,
        "bridge_legal_and_valuation": 1_900.0,
        "broker_fee": 1_500.0,
        "roll_up_interest": True,
        "purchase_deposit_pct": 25.0,
        "purchase_product_fee_pct": 3.0,
        "purchase_rate_pct": 5.4,
    },
    "refinance": {
        "ltv_pct": 75.0,
        "rate_pct": 5.4,
        "product_fee_pct": 3.0,
        "product_fee_added_to_loan": True,
        "icr_pct": 125.0,
        "stress_rate_pct": 5.5,
        "legal_and_valuation": 900.0,
        "broker_fee": 995.0,
    },
    "holding_costs_monthly": {"council_tax": 120.0, "insurance": 50.0,
                              "utilities": 40.0, "other": 0.0},
    "operating_costs": {
        "management_pct": 10.0,
        "maintenance_pct": 5.0,
        "voids_pct": 5.0,
        "insurance_annual": 380.0,
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


def flat_paths(obj, prefix=""):
    """Dotted paths actually present in the user's file, so the report can say
    which figures came from them and which the script filled in. Nobody should
    have to guess which numbers in an appraisal were invented."""
    found = set()
    for key, value in obj.items():
        path = f"{prefix}{key}"
        found.add(path)
        if isinstance(value, dict):
            found |= flat_paths(value, path + ".")
    return found


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
    return deal, flat_paths(raw)


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

    # --- how the purchase is funded ----------------------------------------
    # Three routes. Bridging is the auction default; a BTL mortgage from day one
    # is cheaper but needs a lettable property and a timescale a lender can meet;
    # cash needs no deposit because the whole price is the deposit.
    if fin["method"] == "bridging":
        purchase_loan = price * fin["bridge_ltv_pct"] / 100.0
        arrangement_fee = purchase_loan * fin["bridge_arrangement_fee_pct"] / 100.0
        bridge_interest = purchase_loan * fin["bridge_monthly_rate_pct"] / 100.0 * months
        exit_fee = purchase_loan * fin["bridge_exit_fee_pct"] / 100.0
        if fin["roll_up_interest"]:
            interest_paid_in_cash = 0.0
            redemption = purchase_loan + bridge_interest + exit_fee
        else:
            interest_paid_in_cash = bridge_interest
            redemption = purchase_loan + exit_fee
    elif fin["method"] == "btl_mortgage":
        # A deposit is a real cash outlay at completion, unlike the equity you
        # retain at refinance — which is why it belongs here and not there.
        purchase_loan = price * (100.0 - fin["purchase_deposit_pct"]) / 100.0
        arrangement_fee = purchase_loan * fin["purchase_product_fee_pct"] / 100.0
        bridge_interest = (purchase_loan * fin["purchase_rate_pct"] / 100.0 / 12.0) * months
        exit_fee = 0.0
        interest_paid_in_cash = bridge_interest
        redemption = purchase_loan
    else:
        purchase_loan = arrangement_fee = bridge_interest = exit_fee = 0.0
        interest_paid_in_cash = redemption = 0.0

    bridge_loan = purchase_loan  # kept under the old name for the report
    deposit = price - purchase_loan

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
        "deposit": deposit,
        "retained_equity": value - refi_loan,
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


# How far past a threshold still counts as "nearly". Without these, a deal
# that leaves £6,000 in against a £0 target reads identically to one that
# strands £60,000, and the buyer is told something false.
TOLERANCE = {
    "Money left in": 7_500,                 # pounds over the limit
    "Return on capital left in": 3.0,       # percentage points under
    "Monthly cashflow": 50,                 # pounds a month under
    "Yield on end value": 0.75,             # percentage points under
}


def test_criteria(result, criteria):
    """Every test the deal has to pass, tagged capital or income.

    The split matters more than the individual results. Capital tests ask
    whether you get your money back out; income tests ask whether the thing
    pays you once it is let. A property can be excellent at one and hopeless at
    the other, and in a low-yielding area that is the normal case rather than
    the exception. A flat list of four failures hides which kind of deal this is.

    Each test returns PASS, NEARLY or FAIL. The middle state exists because
    thresholds are chosen round numbers, not cliffs — missing a £0-left-in
    target by £6,000 is a good outcome described badly.
    """
    def status(ok, shortfall, tolerance):
        if ok:
            return "PASS"
        return "NEARLY" if shortfall <= tolerance else "FAIL"

    left = result["money_left_in"]
    limit = criteria["max_money_left_in"]
    roi = result["roi"]
    roi_min = criteria["min_roi_pct"]
    cf = result["monthly_cashflow"]
    cf_min = criteria["min_monthly_cashflow"]
    yld = result["yield_on_value"]
    yld_min = criteria["min_yield_on_value_pct"]

    return [
        ("Money left in", "capital",
         status(left <= limit, left - limit, TOLERANCE["Money left in"]),
         f"£{left:,.0f} vs limit £{limit:,.0f}"),
        ("Return on capital left in", "capital",
         status(roi >= roi_min, roi_min - roi, TOLERANCE["Return on capital left in"]),
         ("all capital recycled" if math.isinf(roi)
          else f"{roi:.1f}% vs minimum {roi_min:.1f}%")),
        ("Monthly cashflow", "income",
         status(cf >= cf_min, cf_min - cf, TOLERANCE["Monthly cashflow"]),
         f"£{cf:,.0f} vs minimum £{cf_min:,.0f}"),
        ("Yield on end value", "income",
         status(yld >= yld_min, yld_min - yld, TOLERANCE["Yield on end value"]),
         f"{yld:.1f}% vs minimum {yld_min:.1f}%"),
    ]


def category_state(tests, category):
    """PASS if every test clears, NEARLY if none hard-fails, else FAIL."""
    states = [st for _, cat, st, _ in tests if cat == category]
    if all(st == "PASS" for st in states):
        return "PASS"
    if any(st == "FAIL" for st in states):
        return "FAIL"
    return "NEARLY"


def classify(result, criteria):
    """Name the kind of deal this is, which is what the buyer needs first."""
    tests = test_criteria(result, criteria)
    cap = category_state(tests, "capital")
    inc = category_state(tests, "income")

    def phrase(state, good, near, bad):
        return {"PASS": good, "NEARLY": near, "FAIL": bad}[state]

    cap_text = phrase(cap,
        "returns your capital",
        "very nearly returns your capital",
        "strands your capital")
    inc_text = phrase(inc,
        "pays you monthly",
        "almost pays you monthly",
        "does not pay you monthly")

    if cap == "FAIL" and inc == "FAIL":
        return "neither", (
            "**This does not work on either measure** — it neither returns your "
            "capital nor pays you monthly.")
    if cap in ("PASS", "NEARLY") and inc == "FAIL":
        lead = "**This is an equity deal, not an income deal.**"
        if cap == "NEARLY":
            lead = ("**This is an equity deal, not an income deal — and it misses "
                    "the capital targets only narrowly.**")
        return "equity", (
            f"{lead} It {cap_text} to redeploy and builds equity, but it "
            "will not pay you meaningfully each month. That is a legitimate thing "
            "to buy, as long as you are buying it knowingly and not expecting "
            "income that is never going to arrive.")
    if inc in ("PASS", "NEARLY") and cap == "FAIL":
        roi_state = next(st for name, _, st, _ in tests
                         if name == "Return on capital left in")
        if roi_state == "FAIL":
            # It pays monthly, but only because a great deal of money is sitting
            # under it. Return on that capital is the test that matters here, and
            # calling this an income deal would flatter it badly.
            return "neither", (
                "**This pays monthly, but it is not a good deal.** It "
                f"{inc_text}, yet it {cap_text} at a return of "
                f"{result['roi']:.1f}% on the money you leave behind. Judge it "
                "against what that capital would earn elsewhere, including in "
                "the next purchase you cannot now make, rather than against the "
                "monthly figure in isolation.")
        return "income", (
            "**This is an income deal, not a capital-recycling one.** It "
            f"{inc_text} at a healthy {result['roi']:.1f}% on the capital left "
            "in, but that capital is not coming back for the next purchase. "
            "Fine if you have money to park; a problem if you are building a "
            "portfolio from a fixed pot.")
    if cap == "PASS" and inc == "PASS":
        return "both", (
            "**This works on both counts** — it returns your capital and it pays "
            "you monthly. That is rare, so check the end value and the rent "
            "harder than usual before believing it.")
    return "both", (
        f"**This broadly works on both counts** — it {cap_text} and it "
        f"{inc_text}, missing the stated targets only narrowly. Judge it on how "
        "much you trust the end value and the rent, not on the near misses.")


def solve_max_offer(deal, criteria_subset=None, strict=False):
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
            tests = [t for t in tests
                     if t[0] in criteria_subset or t[1] in criteria_subset]
        allowed = ("PASS",) if strict else ("PASS", "NEARLY")
        return all(st in allowed for _, _, st, _ in tests)

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


def solve_max_refurb(deal, price, criteria_subset=None):
    """Biggest refurb budget that still works, holding the price still."""
    crit = deal["criteria"]

    def passes(budget):
        d = deepcopy(deal)
        d["purchase_price"] = price
        d["refurb"]["budget"] = budget
        tests = test_criteria(appraise(d), crit)
        if criteria_subset:
            tests = [t for t in tests
                     if t[0] in criteria_subset or t[1] in criteria_subset]
        return all(st != "FAIL" for _, _, st, _ in tests)

    if not passes(0):
        return None
    lo, hi = 0.0, max(deal["post_refurb_value"], 1.0)
    if passes(hi):
        return hi
    for _ in range(50):
        mid = (lo + hi) / 2
        if passes(mid):
            lo = mid
        else:
            hi = mid
    return math.floor(lo / 500.0) * 500.0


def solve_frontier(deal, refurbs=None, criteria_subset=("capital",), strict=True):
    """The pairs of (refurb budget, purchase price) that make the deal work.

    "What should I pay" has no single answer, because what you can pay depends
    entirely on what the works cost — every pound of refurb is a pound you
    cannot put in the offer. Solving the two together gives the buyer a line
    they can negotiate along instead of a number that silently assumes a refurb
    figure they have not confirmed.
    """
    base = deal["refurb"]["budget"]
    if refurbs is None:
        if base <= 0:
            base = deal["post_refurb_value"] * 0.15
        refurbs = [round(base * m / 1000) * 1000
                   for m in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)]
    rows = []
    for budget in sorted(set(refurbs)):
        d = deepcopy(deal)
        d["refurb"]["budget"] = budget
        price = solve_max_offer(d, criteria_subset=set(criteria_subset), strict=strict)
        if price is None:
            rows.append((budget, None, None))
            continue
        d["purchase_price"] = price
        rows.append((budget, price, appraise(d)))
    return rows


def affordability_ceiling(deal):
    """The all-in number every other figure has to fit inside.

    At refinance you can borrow a fixed amount — whichever of the LTV cap and
    the rental stress cap is lower. Add whatever capital you are willing to
    leave behind and you have the total the whole project may cost: purchase,
    tax, fees, works, finance, the lot. It is the cleanest way to see why a
    refurb overrun has to come straight out of the offer.
    """
    result = appraise(deal)
    budget = result["refi_loan"] + deal["criteria"]["max_money_left_in"]
    non_purchase = result["total_project_cost"] - result["purchase_price"]
    return {
        "refi_loan": result["refi_loan"],
        "acceptable_left_in": deal["criteria"]["max_money_left_in"],
        "total_project_budget": budget,
        "non_purchase_costs": non_purchase,
        "implied_price": budget - non_purchase,
        "binding_cap": result["binding_cap"],
        "retained_equity": result["retained_equity"],
    }


def criteria_conflict(deal, ltvs=(55, 60, 65, 70, 75, 80)):
    """Can the capital target and the income target both be met at once?

    In a low-yielding area they usually cannot, and the reason is structural
    rather than a matter of negotiating harder. Borrowing less at refinance buys
    monthly headroom but strands capital; borrowing more recycles the capital but
    the interest eats the rent. The buyer is choosing between two things, not
    failing at one, and they deserve to be told that explicitly rather than left
    to infer it from four red FAILs.

    For each LTV this solves the price that fully recycles the capital and reports
    the cashflow that comes with it, plus the capital that would have to stay in
    to reach the income target instead.
    """
    rows = []
    for ltv in ltvs:
        d = deepcopy(deal)
        d["refinance"]["ltv_pct"] = ltv
        price = solve_max_offer(d, criteria_subset={"Money left in"}, strict=True)
        if price is None:
            rows.append((ltv, None, None, None))
            continue
        recycled = deepcopy(d)
        recycled["purchase_price"] = price
        r = appraise(recycled)
        at_stated = deepcopy(d)
        r2 = appraise(at_stated)
        rows.append((ltv, price, r, r2))
    return rows


def conflict_summary(deal, rows):
    """Whether both targets are reachable, and what has to give if not."""
    crit = deal["criteria"]
    target = crit["min_monthly_cashflow"]
    reachable = [(ltv, price, r) for ltv, price, r, _ in rows
                 if r is not None and r["monthly_cashflow"] >= target]
    best = max((r["monthly_cashflow"] for _, _, r, _ in rows if r is not None),
               default=0.0)
    paying = [(ltv, r2) for ltv, _, _, r2 in rows
              if r2 is not None and r2["monthly_cashflow"] >= target]
    return {
        "both_possible": bool(reachable),
        "best_cashflow_while_recycling": best,
        "cheapest_price_for_both": min((p for _, p, _ in reachable), default=None),
        "capital_needed_for_income": min(
            (r2["money_left_in"] for _, r2 in paying), default=None),
        "target": target,
    }


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


def breakevens(deal):
    """The numbers that would have to change to rescue a failing test.

    "It does not work" is much less useful than "it works if the rent is £790".
    Each of these bisects one input while holding the rest still, so the answer
    is a single figure the buyer can go and verify with an agent or a builder.
    """
    crit = deal["criteria"]
    out = {}

    def bisect(lo, hi, better_is_higher, test):
        """Find where `test` flips between lo and hi, or None if it never does."""
        if better_is_higher:
            if not test(hi):
                return None          # even the top of the range fails
            for _ in range(50):
                mid = (lo + hi) / 2
                if test(mid):
                    hi = mid
                else:
                    lo = mid
            return hi
        if not test(lo):
            return None              # even the bottom of the range fails
        for _ in range(50):
            mid = (lo + hi) / 2
            if test(mid):
                lo = mid
            else:
                hi = mid
        return lo

    def rent_test(rent):
        d = deepcopy(deal); d["monthly_rent"] = rent
        return appraise(d)["monthly_cashflow"] >= crit["min_monthly_cashflow"]

    if not rent_test(deal["monthly_rent"]):
        out["Rent needed to hit the cashflow target"] = bisect(
            deal["monthly_rent"], deal["monthly_rent"] * 3, True, rent_test)

    def value_test(value):
        d = deepcopy(deal); d["post_refurb_value"] = value
        return appraise(d)["money_left_in"] <= crit["max_money_left_in"]

    if not value_test(deal["post_refurb_value"]):
        out["End value needed to hit the money-left-in target"] = bisect(
            deal["post_refurb_value"], deal["post_refurb_value"] * 2.5, True, value_test)

    def refurb_test(budget):
        d = deepcopy(deal); d["refurb"]["budget"] = budget
        return appraise(d)["money_left_in"] <= crit["max_money_left_in"]

    if not refurb_test(deal["refurb"]["budget"]) and refurb_test(0):
        out["Refurb budget you could afford and still hit money left in"] = bisect(
            0, deal["refurb"]["budget"], False, refurb_test)

    return out


def matrix(deal, values=None, refurbs=None):
    """Money left in and on-paper margin across the plausible range.

    A single base case invites false confidence. What a buyer actually needs to
    know is whether the deal survives being wrong about the two inputs they are
    guessing at — so vary both and show the whole grid. If every cell works, the
    deal is robust; if only the optimistic corner works, it is a bet.
    """
    base_value = deal["post_refurb_value"]
    base_refurb = deal["refurb"]["budget"]
    values = values or [round(base_value * m / 1000) * 1000
                        for m in (0.88, 0.96, 1.0, 1.08)]
    refurbs = refurbs or [round(base_refurb * m / 1000) * 1000
                          for m in (1.0, 1.25, 1.55)]
    rows = []
    for value in values:
        cells = []
        for refurb in refurbs:
            d = deepcopy(deal)
            d["post_refurb_value"] = value
            d["refurb"]["budget"] = refurb
            cells.append(appraise(d))
        rows.append((value, cells))
    return values, refurbs, rows


def rent_sensitivity(deal, steps=(-0.1, -0.05, 0.0, 0.05, 0.1, 0.15)):
    """Cashflow against rent. Usually the input with the most leverage left."""
    rows = []
    for step in steps:
        d = deepcopy(deal)
        d["monthly_rent"] = round(deal["monthly_rent"] * (1 + step) / 5) * 5
        rows.append((d["monthly_rent"], appraise(d)))
    return rows


# The full input register. Everything the model reads appears here, so the
# report can show the buyer every figure their answer rests on and mark which
# ones they supplied. A number nobody can see is a number nobody can challenge.
ASSUMPTION_SPEC = [
    ("The three that decide everything", [
        ("Post-refurb value", "post_refurb_value", "money"),
        ("Achievable monthly rent", "monthly_rent", "money"),
        ("Refurb budget", "refurb.budget", "money"),
    ]),
    ("Purchase", [
        ("Purchase price modelled", "purchase_price", "money"),
        ("Tax basis", "ltt_basis", "text"),
        ("Auction buyer premium or reservation fee", "purchase_costs.auction_buyer_premium", "money"),
        ("Auction admin fee", "purchase_costs.auction_admin_fee", "money"),
        ("Seller costs passed to buyer", "purchase_costs.seller_costs_payable_by_buyer", "money"),
        ("Solicitor", "purchase_costs.solicitor_purchase", "money"),
        ("Searches", "purchase_costs.searches", "money"),
        ("Survey", "purchase_costs.survey", "money"),
        ("LTT return filing", "purchase_costs.ltt_filing", "money"),
        ("Other purchase costs", "purchase_costs.other", "money"),
    ]),
    ("Works", [
        ("Contingency on the works", "refurb.contingency_pct", "pct"),
        ("Months from purchase to refinance", "refurb.months", "months"),
    ]),
    ("Funding the purchase", [
        ("Method", "finance.method", "text"),
        ("Bridge loan to value", "finance.bridge_ltv_pct", "pct"),
        ("Bridge interest", "finance.bridge_monthly_rate_pct", "pct_month"),
        ("Bridge arrangement fee", "finance.bridge_arrangement_fee_pct", "pct"),
        ("Bridge exit fee", "finance.bridge_exit_fee_pct", "pct"),
        ("Bridge legal and valuation", "finance.bridge_legal_and_valuation", "money"),
        ("Broker fee", "finance.broker_fee", "money"),
        ("Interest rolled up rather than paid monthly", "finance.roll_up_interest", "bool"),
        ("Deposit if bought on a BTL mortgage", "finance.purchase_deposit_pct", "pct"),
    ]),
    ("Refinance", [
        ("Loan to value", "refinance.ltv_pct", "pct"),
        ("Rate", "refinance.rate_pct", "pct"),
        ("Product fee", "refinance.product_fee_pct", "pct"),
        ("Product fee added to the loan", "refinance.product_fee_added_to_loan", "bool"),
        ("Interest cover required", "refinance.icr_pct", "pct"),
        ("Stress rate", "refinance.stress_rate_pct", "pct"),
        ("Legal and valuation", "refinance.legal_and_valuation", "money"),
        ("Broker fee", "refinance.broker_fee", "money"),
    ]),
    ("Holding costs while the works run, per month", [
        ("Council tax", "holding_costs_monthly.council_tax", "money"),
        ("Insurance", "holding_costs_monthly.insurance", "money"),
        ("Utilities", "holding_costs_monthly.utilities", "money"),
        ("Other", "holding_costs_monthly.other", "money"),
    ]),
    ("Operating costs once let", [
        ("Letting management", "operating_costs.management_pct", "pct_rent"),
        ("Maintenance reserve", "operating_costs.maintenance_pct", "pct_rent"),
        ("Voids reserve", "operating_costs.voids_pct", "pct_rent"),
        ("Landlord insurance", "operating_costs.insurance_annual", "money_year"),
        ("Ground rent and service charge", "operating_costs.ground_rent_and_service_charge_annual", "money_year"),
        ("Other annual costs", "operating_costs.other_annual", "money_year"),
    ]),
    ("Your criteria", [
        ("Maximum money left in", "criteria.max_money_left_in", "money"),
        ("Minimum monthly cashflow", "criteria.min_monthly_cashflow", "money"),
        ("Minimum return on capital left in", "criteria.min_roi_pct", "pct"),
        ("Minimum yield on end value", "criteria.min_yield_on_value_pct", "pct"),
    ]),
]


def dig(deal, path):
    node = deal
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def render_value(value, kind):
    if value is None:
        return "—"
    if kind == "money":
        return f"£{value:,.0f}"
    if kind == "money_year":
        return f"£{value:,.0f} a year"
    if kind == "pct":
        return f"{value:g}%"
    if kind == "pct_month":
        return f"{value:g}% a month"
    if kind == "pct_rent":
        return f"{value:g}% of rent"
    if kind == "months":
        return f"{value:g} months"
    if kind == "bool":
        return "yes" if value else "no"
    return str(value).replace("_", " ")


def assumption_rows(deal, provided):
    """Every input, its value and whether the buyer supplied it."""
    sections = []
    method = deal["finance"]["method"]
    for title, entries in ASSUMPTION_SPEC:
        rows = []
        for label, path, kind in entries:
            # Do not clutter the register with terms that this deal never uses.
            if path.startswith("finance.bridge") and method != "bridging":
                continue
            if path == "finance.roll_up_interest" and method != "bridging":
                continue
            if path == "finance.purchase_deposit_pct" and method != "btl_mortgage":
                continue
            value = dig(deal, path)
            if value is None:
                continue
            rows.append((label, render_value(value, kind),
                         "yours" if path in provided else "assumed"))
        if rows:
            sections.append((title, rows))
    return sections


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def money(x):
    return f"£{x:,.0f}"


def report(deal, result, provided=frozenset(), max_offer=None,
           show_sensitivity=True, show_solve=False):
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
    for label, path, _ in ASSUMPTION_SPEC[1][1]:
        if not path.startswith("purchase_costs."):
            continue
        amount = dig(deal, path)
        if amount:
            add(f"| {label} | {money(amount)} |")
    add(f"| Refurb budget | {money(result['refurb_budget'])} |")
    add(f"| Refurb contingency | {money(result['refurb_contingency'])} |")
    if result["bridge_arrangement_fee"]:
        add(f"| Lender arrangement fee | {money(result['bridge_arrangement_fee'])} |")
    if deal["finance"]["bridge_legal_and_valuation"]:
        add(f"| Lender legal and valuation | "
            f"{money(deal['finance']['bridge_legal_and_valuation'])} |")
    if deal["finance"]["broker_fee"]:
        add(f"| Broker fee | {money(deal['finance']['broker_fee'])} |")
    if result["interest_paid_in_cash"]:
        add(f"| Bridge interest paid monthly | {money(result['interest_paid_in_cash'])} |")
    months_held = deal["refurb"]["months"]
    monthly_hold = sum(deal["holding_costs_monthly"].values())
    add(f"| Holding costs, {monthly_hold:,.0f}/month over {months_held:g} months "
        f"| {money(result['holding_costs'])} |")
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

    if show_solve:
        ceiling = affordability_ceiling(deal)
        add("## What you need to buy it for")
        add("")
        add("Everything has to fit inside one number: what you can borrow when you "
            "refinance, plus whatever capital you are willing to leave behind.")
        add("")
        add("| | |")
        add("| --- | ---: |")
        add(f"| Loan available at refinance (limited by the {ceiling['binding_cap']}) "
            f"| {money(ceiling['refi_loan'])} |")
        add(f"| Capital you have said you will leave in "
            f"| {money(ceiling['acceptable_left_in'])} |")
        add(f"| **Total the whole project may cost** "
            f"| **{money(ceiling['total_project_budget'])}** |")
        add(f"| Less everything that is not the purchase price "
            f"| ({money(ceiling['non_purchase_costs'])}) |")
        add(f"| **Leaves for the purchase** | **{money(ceiling['implied_price'])}** |")
        add("")
        add(f"The {money(ceiling['retained_equity'])} of equity left in the property "
            "after refinancing is not a deposit you hand over — it is the part of the "
            "value the lender will not lend against, so it is money you cannot get "
            "back out. That is precisely what the money-left-in test measures, and it "
            "is why it usually decides the maximum price.")
        add("")

        add("## Price and refurb are the same decision")
        add("")
        add("Every pound the works cost is a pound you cannot put in the offer, so "
            "there is no single maximum price — there is a line you can negotiate "
            "along. Find your honest refurb figure in the left column and read across.")
        add("")
        add("| If the refurb costs | Pay no more than | Total project cost |")
        add("| ---: | ---: | ---: |")
        rows = solve_frontier(deal)
        for budget, price, row in rows:
            if price is None:
                add(f"| {money(budget)} | no price works | — |")
            else:
                add(f"| {money(budget)} | **{money(price)}** | "
                    f"{money(row['total_project_cost'])} |")
        add("")
        priced = [(b, p) for b, p, _ in rows if p is not None]
        if len(priced) >= 2:
            (b0, p0), (b1, p1) = priced[0], priced[-1]
            rate = (p0 - p1) / (b1 - b0) if b1 != b0 else 0
            add(f"Every extra £1,000 of works costs you about £{rate * 1000:,.0f} of "
                "purchase price — more than pound for pound, because the works carry "
                "contingency while the price carries tax and finance. A refurb "
                "estimate that turns out optimistic does not just cost you the "
                "overrun; it means you overpaid by more than the overrun.")
        add("")
        at_price = solve_max_refurb(deal, deal["purchase_price"],
                                    criteria_subset={"capital"})
        if at_price is None:
            add(f"At your stated price of {money(deal['purchase_price'])} the deal "
                "fails on capital even with no works at all.")
        else:
            add(f"Put the other way round: at {money(deal['purchase_price'])} the "
                f"works must come in **under {money(at_price)}** "
                f"(you have budgeted {money(deal['refurb']['budget'])}).")
        add("")

    add("## Verdict")
    add("")
    kind, verdict_text = classify(result, crit)
    add(verdict_text)
    add("")
    add("| Test | | Result | |")
    add("| --- | --- | --- | --- |")
    tests = test_criteria(result, crit)
    for name, category, state, detail in tests:
        add(f"| {name} | {category} | {detail} | {state} |")
    add("")

    gaps = breakevens(deal)
    if gaps:
        add("What would have to change to close the gaps:")
        add("")
        for label, figure in gaps.items():
            if figure is None:
                add(f"- {label}: no achievable figure — this test cannot be met by "
                    "moving that input alone.")
            elif "Rent" in label:
                add(f"- {label}: **£{figure:,.0f} a month** "
                    f"(you have assumed £{deal['monthly_rent']:,.0f}).")
            elif "End value" in label:
                add(f"- {label}: **£{figure:,.0f}** "
                    f"(you have assumed £{deal['post_refurb_value']:,.0f}).")
            else:
                add(f"- {label}: **£{figure:,.0f}** "
                    f"(you have budgeted £{deal['refurb']['budget']:,.0f}).")
        add("")
        add("These are single figures you can go and check with an agent, a builder "
            "or a broker. Each one holds everything else still, so treat them as "
            "the question to answer next rather than as a forecast.")
        add("")

    if max_offer is not None:
        add("## Maximum offer")
        add("")
        cap = solve_max_offer(deal, criteria_subset={"capital"})
        inc = solve_max_offer(deal, criteria_subset={"income"})
        both = None if max_offer is False else max_offer

        add("| Judged on | Highest price that still passes |")
        add("| --- | ---: |")
        for label, ceiling in (("Capital tests (money back out)", cap),
                               ("Income tests (what it pays monthly)", inc),
                               ("Everything together", both)):
            if ceiling is None:
                text = "no price works"
            elif ceiling >= deal["post_refurb_value"] * 1.49:
                text = "not price-sensitive"
            else:
                text = money(ceiling)
            add(f"| {label} | {text} |")
        add("")

        if inc is None and cap is not None:
            add(f"**Offer no more than {money(cap)}** if you are buying this to "
                "recycle capital. No price makes the income tests pass, so do not "
                "negotiate in the belief that a lower purchase fixes the monthly "
                "figure — it does not. After refinancing your debt is set by the "
                "end value and the rent, not by what you paid.")
            add("")
            add("There is a trap in that worth spelling out: because the loan is a "
                "percentage of the end value, a *higher* valuation borrows more and "
                "cashflows *worse*. A stronger survey result is not automatically "
                "good news for the monthly position.")
        elif both is None:
            add("No price passes everything, and the capital tests fail too. The "
                "problem is the end value, the rent, the refurb cost or the finance "
                "terms — not the asking price.")
        else:
            add(f"**Offer no more than {money(both)}** to satisfy every test.")
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
        rows = criteria_conflict(deal)
        summary = conflict_summary(deal, rows)
        if not summary["both_possible"]:
            add("## Can you have both?")
            add("")
            add("No. On this property your capital target and your income target "
                "cannot both be met, at any price and at any loan-to-value. That is "
                "not a negotiating problem — it is what the rent supports.")
            add("")
            add("| Refinance LTV | Price to fully recycle | Cashflow you get | "
                "Or: capital left in at your price |")
            add("| ---: | ---: | ---: | ---: |")
            for ltv, price, r, r2 in rows:
                if r is None:
                    add(f"| {ltv}% | no price works | — | — |")
                    continue
                add(f"| {ltv}% | {money(price)} | {money(r['monthly_cashflow'])} | "
                    f"{money(r2['money_left_in'])} |")
            add("")
            add(f"The most this can pay while still returning all your capital is "
                f"{money(summary['best_cashflow_while_recycling'])} a month, against "
                f"a target of {money(summary['target'])}.")
            if summary["capital_needed_for_income"] is not None:
                add(f" To reach {money(summary['target'])} instead, you would leave "
                    f"about {money(summary['capital_needed_for_income'])} in at your "
                    "stated price.")
            add("")
            add("Pick deliberately. Maximum leverage gives the best return on the "
                "capital you leave behind and the worst monthly figure; minimum "
                "leverage does the reverse. Neither is wrong, but buying at maximum "
                "LTV and then being disappointed by the cashflow is a decision made "
                "by accident.")
            add("")
        add("## Is it robust, or is it a bet?")
        add("")
        add("Money left in, and on-paper margin, across the range you might be wrong "
            "over. Your base case is one cell of this grid.")
        add("")
        values, refurbs, rows = matrix(deal)
        add("| End value | " + " | ".join(f"refurb {money(r)}" for r in refurbs) + " |")
        add("| ---: | " + " | ".join("---:" for _ in refurbs) + " |")
        for value, cells in rows:
            cs = [f"{money(c['money_left_in'])} in / {c['profit_on_paper']:+,.0f}"
                  for c in cells]
            add(f"| {money(value)} | " + " | ".join(cs) + " |")
        add("")
        negative = sum(1 for _, cells in rows for c in cells if c["profit_on_paper"] < 0)
        total = sum(len(cells) for _, cells in rows)
        if negative == 0:
            add("Every cell makes money. The deal survives being wrong about both the "
                "end value and the refurb, which is the strongest thing that can be "
                "said about a BRRR before you own it.")
        elif negative == total:
            add("No cell makes money. This is not a question of being cautious with "
                "your assumptions — the deal does not work anywhere in the plausible "
                "range.")
        else:
            add(f"{negative} of {total} cells lose money. The deal works, but only if "
                "you are right about the inputs — treat the optimistic corner as a "
                "bet rather than a plan, and size your contingency accordingly.")
        add("")

        add("## What the rent does")
        add("")
        add("| Rent | Gross yield | Monthly cashflow |")
        add("| ---: | ---: | ---: |")
        for rent, row in rent_sensitivity(deal):
            marker = " *" if abs(rent - deal["monthly_rent"]) < 1 else ""
            add(f"| {money(rent)}{marker} | {row['yield_on_value']:.1f}% | "
                f"{money(row['monthly_cashflow'])} |")
        add("")
        add("Rent is usually the input with the most leverage still in it and the "
            "easiest to verify — a letting agent will give you a real figure in a "
            "phone call. Where the monthly position is marginal, this is the number "
            "to nail down before anything else.")
        add("")

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


    add("")
    add("## Every figure this rests on")
    add("")
    assumed = sum(1 for _, rows in assumption_rows(deal, provided)
                  for _, _, src in rows if src == "assumed")
    add(f"Marked *yours* where you gave me the number and *assumed* where I filled "
        f"it in from market typicals. {assumed} figures here are mine, not yours — "
        "they are reasonable starting points, not quotes, and any of them can move "
        "the answer. Correct the ones you know and I will re-run.")
    add("")
    for title, rows in assumption_rows(deal, provided):
        add(f"**{title}**")
        add("")
        add("| Figure | Value | Source |")
        add("| --- | ---: | --- |")
        for label, value, source in rows:
            add(f"| {label} | {value} | {source} |")
        add("")

    return "\n".join(lines)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deal", help="path to the deal JSON file")
    parser.add_argument("--max-offer", action="store_true",
                        help="also solve for the highest price that meets every criterion")
    parser.add_argument("--no-sensitivity", action="store_true")
    parser.add_argument("--solve", action="store_true",
                        help="solve the purchase price and refurb budget together")
    parser.add_argument("--json", action="store_true", help="emit raw numbers instead of a report")
    args = parser.parse_args()

    deal, provided = load_deal(args.deal)
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

    print(report(deal, result, provided=provided, max_offer=max_offer,
                 show_sensitivity=not args.no_sensitivity, show_solve=args.solve))


if __name__ == "__main__":
    main()
