# Land Transaction Tax — Wales

**Rates verified: September 2026.** Welsh Government has changed the higher rates
mid-year before (most recently overnight on 11 December 2024, with one day's
notice). If an appraisal turns on the tax figure, confirm at
<https://www.gov.wales/land-transaction-tax-rates-and-bands> before the user
commits.

LTT replaced Stamp Duty Land Tax in Wales on 1 April 2018. It is administered by
the Welsh Revenue Authority, not HMRC. The return must be filed and the tax paid
within **30 days of completion** — shorter than England's 14 days is long, and a
common trip-up for solicitors who mostly act in England.

## Higher residential rates — what a company pays

*Effective 11 December 2024.*

A company buying a dwelling pays higher residential rates on **every pound**.
There is no nil-rate band. This is not a surcharge added on top of the main
rates, as it is in England — since December 2024 Wales uses a completely separate
schedule.

| Price band | Rate |
| --- | ---: |
| £0 – £180,000 | 5% |
| £180,000 – £250,000 | 8.5% |
| £250,000 – £400,000 | 10% |
| £400,000 – £750,000 | 12.5% |
| £750,000 – £1,500,000 | 15% |
| Above £1,500,000 | 17% |

Worked examples at typical North Wales price points:

| Price | LTT | Effective rate |
| ---: | ---: | ---: |
| £60,000 | £3,000 | 5.0% |
| £95,000 | £4,750 | 5.0% |
| £150,000 | £7,500 | 5.0% |
| £180,000 | £9,000 | 5.0% |
| £250,000 | £14,950 | 6.0% |
| £400,000 | £29,950 | 7.5% |

Note how flat this is below £180,000. Across most of the Conwy and Denbighshire
terraced market, LTT is simply 5% of the price, which makes it easy to sanity-check
the script's output by eye.

## The £40,000 floor

Higher rates do not apply where the consideration is **under £40,000**. Below that
the main residential rates apply, and since those start at 0% up to £225,000, the
tax is nil.

This is a genuine cliff edge, not a taper. £39,999 attracts no tax; £40,000
attracts £2,000. On very cheap lots — and they exist in parts of North Wales —
this is worth knowing before bidding, though be aware the WRA looks at linked
transactions and will aggregate connected purchases.

## When higher rates apply

For an SPV the answer is always: a company acquiring a dwelling pays higher rates
regardless of whether it owns anything else. There is no first-property exemption
for companies.

For an individual, higher rates apply if they will own more than one dwelling at
the end of the transaction and the other dwelling is worth £40,000 or more,
anywhere in the world.

## Main residential rates

*Effective 10 October 2022.* These apply to an individual buying a sole or main
residence, and to any purchase under £40,000.

| Price band | Rate |
| --- | ---: |
| £0 – £225,000 | 0% |
| £225,000 – £400,000 | 6% |
| £400,000 – £750,000 | 7.5% |
| £750,000 – £1,500,000 | 10% |
| Above £1,500,000 | 12% |

Wales has **no first-time buyer relief** — unlike England. The £225,000 nil-rate
band applies to everyone buying a main home, which is why the relief was dropped.

## Non-residential rates

*Effective 22 December 2020.*

| Price band | Rate |
| --- | ---: |
| £0 – £225,000 | 0% |
| £225,000 – £250,000 | 1% |
| £250,000 – £1,000,000 | 5% |
| Above £1,000,000 | 6% |

Relevant to a BRRR buyer in three situations, all worth checking because the
saving is large — on a £200,000 purchase it is the difference between £10,700 and
nil.

**Mixed use.** A property with both residential and commercial elements — a flat
over a shop is the classic — is taxed wholly at non-residential rates. The
commercial element has to be real and in genuine use, not a token arrangement.

**Six or more dwellings.** A single transaction of six or more dwellings is
treated as non-residential. This is a rule, not a relief to claim, and it is why
small blocks trade differently from the sum of their flats. Note that Multiple
Dwellings Relief was abolished across the UK in June 2024, so this rule is now
the main volume play.

**Derelict property.** A building so derelict it is not "suitable for use as a
dwelling" may fall outside residential rates. The bar is much higher than most
investors assume: a property needing a full refurbishment, a new kitchen,
rewiring and a new roof is still a dwelling. It has to be closer to a shell —
structurally unsound, or stripped of the fundamental characteristics of a
dwelling. Do not model this basis without the user confirming their solicitor
supports it, and flag that the WRA may challenge it after completion.

## Other jurisdictions

If the property turns out not to be in Wales, the model needs a different tax
basis and this skill's script does not cover them. The headline positions:

**England and Northern Ireland — SDLT.** Additional-property surcharge of 5% on
top of the standard bands (0% to £125,000, 2% to £250,000, 5% to £925,000, 10% to
£1.5m, 12% above), so a company pays 5%/7%/10%/15%/17%. A company purchase above
£500,000 is charged a flat 17% unless a relief such as property rental business
relief applies — that relief is the norm for genuine BTL SPVs but it must be
claimed, and it is withdrawn if the property is occupied by a connected person.

**Scotland — LBTT.** Additional Dwelling Supplement of 8% on the full price, on
top of standard LBTT bands.

Check current rates rather than relying on these summaries; they move at every
Budget.
