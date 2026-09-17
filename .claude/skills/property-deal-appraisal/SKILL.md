---
name: property-deal-appraisal
description: Appraise a UK property investment and work out the maximum price worth paying for it. Use this whenever the user is weighing up a property purchase — an auction lot, a listing they have found, a guide price they are wondering about, "is this a good deal", "what should I offer", "would this stack up", "what's my max bid", or any question involving rental yield, refurb costs, refinancing, money left in, stamp duty / LTT, or whether a BRRR deal works. Use it even when they only give a price and an address, and especially when they are about to bid or make an offer — the whole point is to establish the ceiling before they commit. Covers Welsh Land Transaction Tax for company (SPV) purchases, auctioneer and solicitor fees, bridging finance and refinance stress tests.
---

# Property deal appraisal

This skill answers two questions about a property, in order:

1. **Does this deal work at all?**
2. **If so, what is the most I should pay?**

The default frame is **BRRR** — buy, refurbish, refinance, rent — bought through a
**limited company SPV** in **Wales**, so the tax is Land Transaction Tax at higher
residential rates. If the user is buying somewhere else, in their own name, or to
flip rather than hold, say so and adjust rather than silently running the wrong
model; `references/ltt-wales.md` covers the other tax bases.

## Why this needs care

BRRR appraisal defeats intuition in a specific way, and the whole value of this
skill is in getting that one thing right:

> **Your debt after refinancing is set by the end value and the rent — not by what
> you paid.** Paying less does not improve your monthly cashflow by a single pound.
> It only changes how much of your own capital stays trapped in the deal.

So "what's my maximum price" is really a question about capital recycling, and a
deal that fails on cashflow or yield cannot be rescued by bidding lower. People
lose money by negotiating hard on a property that was never going to cashflow.
Make this explicit whenever it applies — it is usually the most useful thing you
will tell them.

## Workflow

### 1. Gather the deal

You need eleven numbers, but only three of them really matter. Ask for what is
missing rather than guessing, and be direct that the answer is only as good as
these inputs.

**The three that decide everything:**

| Input | Why it dominates |
| --- | --- |
| Post-refurb value | Sets the refinance loan, so it sets the money you get back |
| Achievable monthly rent | Sets the cashflow and can cap the loan via the stress test |
| Refurb cost | The number most often underestimated, and it comes straight out of your pocket |

If the user offers these as round guesses, push back once. `references/valuation-evidence.md`
covers how to establish them defensibly — sold comparables rather than asking
prices, let comparables rather than listings, and a refurb figure built from a
schedule of works rather than a per-square-foot rule of thumb. A deal appraisal
built on an optimistic end value is not a cautious appraisal with a margin of
error; it is a confident answer to the wrong question.

**Everything else** — purchase costs, finance terms, operating assumptions —
has sensible defaults in `references/cost-benchmarks.md`. Use those defaults,
but tell the user which ones you used and what they are, because auction fees
in particular are large, buyer-paid, and routinely missed until contracts are
exchanged.

Watch for these, which change the numbers materially:

- **Auction type.** A traditional auction charges a buyer's premium of roughly
  £1,500–£3,000. The "modern method" charges the *buyer* a reservation fee of
  around 4.5% including VAT, subject to a minimum near £6,600 — on a £100,000
  lot that is 6.6% of the price, and it does not count towards the purchase.
  Always establish which one it is.
- **Whether the seller's legal costs and search pack are passed to the buyer.**
  Common in auction legal packs, typically £1,000–£1,500.
- **Whether the property is habitable.** A genuinely derelict building may fall
  outside residential LTT rates, which is worth tens of thousands. It is also a
  contested area — see `references/ltt-wales.md` before relying on it.

### 2. Run the model

Write the inputs to a JSON file and run the calculator. Do not attempt the
arithmetic yourself: it compounds a step-function tax, a rolled-up bridging
facility, two competing loan caps and a sensitivity grid, and small drifts change
the recommendation.

```bash
python3 scripts/appraise.py deal.json --max-offer
```

`scripts/example-deal.json` is a complete, realistic input file — copy it and
edit. Any field you leave out falls back to a documented default.

The script produces the money-in table, the refinance position, the post-let
cashflow, the verdict against the user's criteria, the maximum offer with a
per-criterion breakdown, a leverage trade-off table and a sensitivity grid.

### 3. Give a verdict, not a spreadsheet

Report the script's findings, but lead with the answer. The user wants to know
whether to bid and what their ceiling is, so open with that in one or two
sentences and let the tables support it.

Then make sure these land, because they are where the judgement lives:

- **The binding constraint.** Which single test stops them paying more, and what
  would have to change to move it.
- **The leverage trade-off.** Maximum LTV is not automatically right. At current
  rates the return on capital is often nearly flat across the LTV range, which
  means borrowing more buys no extra return and simply converts monthly headroom
  into recycled capital. If that is what the table shows, say so plainly.
- **What breaks it.** A down-valuation at refinance is the most common way these
  deals fail. If a 10% shortfall strands more capital than the user can afford,
  the deal has no margin for error whatever the base case says.

### 4. Be honest about the downside

If the deal does not work, say it does not work and say why in one line. Do not
soften it by presenting a max offer so far below the guide price that it is
really a polite refusal — if the ceiling is 40% under the guide, the useful
message is "this is not a deal, it is a different property at a different price".

Equally, do not manufacture doubt about a deal that stacks up well. If the
numbers clear every test with room to spare, say so.

## Criteria

If the user has not told you their thresholds, use these and state that you have:

| Test | Default |
| --- | --- |
| Money left in after refinance | £0 — full capital recycle |
| Monthly cashflow | £200 per property |
| Return on capital left in | 15% |
| Yield on end value | 7% |

£0 left in is the textbook BRRR target and a demanding one in the current rate
environment. Many workable deals leave £10,000–£25,000 in. If the user's stated
criteria make every deal in their area impossible, that is worth telling them —
it usually means the criteria need revisiting, not that the market has no deals.

## Scope and limits

This models the deal, not the user's tax position. Corporation tax on rental
profit, director's loan treatment, extracting money from the SPV, capital
allowances and the eventual disposal are all outside what the script computes,
and they change the real after-tax return. Mention this once; do not pretend to
advise on it.

Rates and thresholds move. The LTT tables carry an "as at" date in
`references/ltt-wales.md` — if the appraisal turns on a tax figure and the date
is stale, check gov.wales before the user relies on it.

You are not a valuer, a broker or an accountant, and a real deal should have a
survey behind the refurb figure and a broker behind the finance terms. Say so
once, at the end, without hedging every number that precedes it.

## Reference files

- `references/ltt-wales.md` — LTT bands for company purchases, the £40,000 floor,
  the six-dwellings rule, derelict property, and the England/Scotland bases
- `references/cost-benchmarks.md` — default fee assumptions with typical ranges
- `references/valuation-evidence.md` — establishing end value, rent and refurb cost
