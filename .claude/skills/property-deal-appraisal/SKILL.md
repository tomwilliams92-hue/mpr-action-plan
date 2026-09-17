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

### 3. Write it up the way a buyer reads it

The script gives you the numbers. The write-up is where the judgement goes, and
it should follow this shape, because it is the order the decision actually gets
made in.

**Open with the verdict in one sentence, classified.** Not "here is the
analysis" — the answer. The script's `## Verdict` section names the kind of deal
it is, and that classification is the single most useful thing you can lead
with, because "yes, but as an equity deal rather than an income one" is a
genuinely different answer from "yes".

**Then the headline table.** Project cost against end value, margin, money left
in, cashflow. Four or five rows. If you are revisiting a deal after the user
changed an input, put the before and after side by side and say which change did
the work — people learn far more from "dropping the refurb moved it more than
the price did" than from a fresh set of numbers.

**Then the constraint, explained.** Which test binds and why. If income tests
fail at any price, say plainly that negotiating harder will not fix the monthly
figure, and say why: the debt after refinancing is set by the end value and the
rent, not by what was paid. Include the inversion when it applies — a higher
valuation borrows more and cashflows worse, so a strong survey is not
automatically good news.

**Then robustness.** The grid answers a question the base case cannot: is this a
deal, or a bet? "Every cell makes money" and "only the optimistic corner works"
deserve very different responses from the buyer.

**Then what to go and check.** The break-even figures are the most actionable
output in the whole report — a rent, an end value, a refurb ceiling. Frame them
as the next phone call, not as a forecast. Close with the single number that
would change your answer, because that tells the user where to spend their
effort.

Keep the tables; drop the parts of the script output that do not carry the
argument. Reproducing all of it is not a report, it is a dump.

### 4. Read the listing for what it does not say

The numbers are only half of it. Listings carry recurring tells, and the ones
that matter are usually costs or risks the appraisal cannot see. Work through
`references/listing-red-flags.md` for any real property — the EPC and heating
combination in particular has killed more lettings plans than any refurb
overrun, and "EPC: Awaiting" on an electrically-heated solid-wall property is a
reason to pause rather than a formality.

Flag what you find as specific things to close before bidding, with the reason
attached. Three or four real ones beat a generic caveat list.

### 5. Be honest in both directions

If the deal does not work, say so in one line and say why. Do not soften it with
a maximum offer so far below the guide that it is really a polite refusal — if
the ceiling is 40% under, the useful message is that this is a different
property at a different price.

Equally, do not manufacture doubt about a deal that stacks up. If the grid is
green everywhere and the tests clear, say so plainly.

And check the price is gettable before building on it. A guide price at modern
auction sits *below* the reserve, usually by around 10%, so appraising at the
guide flatters every number. If the user's target price is below the guide,
tell them they are fishing for an unsold lot rather than bidding for it.

## Criteria

If the user has not told you their thresholds, use these and state that you have:

| Test | Category | Default |
| --- | --- | --- |
| Money left in after refinance | capital | £0 — full recycle |
| Return on capital left in | capital | 15% |
| Monthly cashflow | income | £200 per property |
| Yield on end value | income | 7% |

The capital/income split is deliberate and worth explaining to the user at least
once. Capital tests ask whether you get your money back to buy the next one;
income tests ask whether the thing pays you while you hold it. In a low-yielding
area a property routinely passes one and fails the other, and a flat list of
four failures hides which.

The script also reports NEARLY rather than FAIL where a test misses by a small
margin, because these thresholds are round numbers rather than cliffs. Leaving
£6,000 in against a £0 target is a good result described badly, and reporting it
as a failure would mislead. Treat a near miss as a pass with a note.

£0 left in is the textbook BRRR target and demanding in the current rate
environment; many workable deals leave £10,000–£25,000 in. If the user's
criteria make every deal in their area impossible, say so — that usually means
the criteria need revisiting, not that the market has none.

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
- `references/listing-red-flags.md` — what to extract from a listing and what it costs
