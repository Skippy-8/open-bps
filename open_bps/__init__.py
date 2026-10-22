"""open-bps: screening of building performance standard gaps and penalty exposure from public data.

Every number this package produces is a screening estimate, not a compliance determination, legal
advice or investment advice. See DISCLAIMER.
"""
__version__ = "0.2.0"

DISCLAIMER = (
    "Screening estimate from public data under the cited rules. Not a compliance determination, not legal, "
    "engineering or investment advice. Official figures come only from the jurisdiction (DC DOEE, Denver CASR, "
    "NYC DOB, Boston Environment Department)."
)


def __getattr__(name):
    if name == "PortfolioAnalyzer":           # imported lazily so `import open_bps` stays light
        from open_bps.analyzer import PortfolioAnalyzer
        return PortfolioAnalyzer
    raise AttributeError(name)
