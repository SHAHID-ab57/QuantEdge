"""Pure isolated-margin arithmetic (`app.paper_trading.margin`): liquidation
and bankruptcy prices, unrealized PnL, funding payments.

**The liquidation formula's verification status is pinned here, honestly.**
`TestDeltaDocumentedExamples` reproduces Delta's only published worked
examples and shows they are for an *inverse* contract, so they cannot confirm
the *linear* formula the engine uses for ETHUSD/BTCUSD (USD-margined).
`TestLinearFormulaFollowsDeltasDefinition` checks that the linear formula
satisfies Delta's own stated liquidation condition (a self-consistency check,
not an independent one). `TestVerifiedLinearReference` is the slot for a real
linear-contract figure read from Delta's liquidation-price calculator; it is
skipped until one is added, so the gap shows up in every test run rather than
being forgotten.
"""

from decimal import Decimal

import pytest

from app.paper_trading.margin import (
    bankruptcy_price,
    effective_leverage,
    funding_payment,
    gapped_through_bankruptcy,
    initial_margin,
    is_liquidated,
    liquidation_price,
    position_equity,
    unrealized_pnl,
)

D = Decimal
MM = D("0.0025")  # Delta's minimum maintenance margin for ETHUSD/BTCUSD (0.25%)


def liq(side: str, entry: str, qty: str, leverage: str, mm: Decimal = MM) -> Decimal | None:
    entry_d, qty_d = D(entry), D(qty)
    return liquidation_price(
        side=side,  # type: ignore[arg-type]
        entry_price=entry_d,
        quantity=qty_d,
        margin=initial_margin(notional=entry_d * qty_d, leverage=D(leverage)),
        maintenance_margin_rate=mm,
    )


class TestUnrealizedPnlAndEquity:
    def test_a_long_gains_when_price_rises_and_a_short_when_it_falls(self) -> None:
        kwargs = {"entry_price": D("2000"), "quantity": D("3")}
        assert unrealized_pnl(side="long", price=D("2100"), **kwargs) == D("300")
        assert unrealized_pnl(side="short", price=D("2100"), **kwargs) == D("-300")
        assert unrealized_pnl(side="short", price=D("1900"), **kwargs) == D("300")

    def test_position_equity_of_a_1x_long_is_exactly_quantity_times_price(self) -> None:
        """The generalization must reproduce the value the long-only engine
        always used for a position: `quantity * price`."""
        equity = position_equity(
            side="long",
            entry_price=D("1000.5"),
            price=D("1234.56"),
            quantity=D("2"),
            margin=D("1000.5") * D("2"),
        )
        assert equity == D("1234.56") * D("2")

    def test_initial_margin_is_notional_over_leverage(self) -> None:
        assert initial_margin(notional=D("10000"), leverage=D("5")) == D("2000")
        assert initial_margin(notional=D("10000"), leverage=D("1")) == D("10000")


class TestClosedFormValues:
    def test_a_10x_long_at_2000(self) -> None:
        # bankruptcy E(1-IM) = 1800; liquidation E(1-IM)/(1-MM) = 1800/0.9975
        assert liq("long", "2000", "1", "10") == pytest.approx(D("1804.511278"), abs=D("1e-5"))
        assert bankruptcy_price(
            side="long", entry_price=D("2000"), quantity=D("1"), margin=D("200")
        ) == D("1800")

    def test_a_10x_short_at_2000(self) -> None:
        # bankruptcy E(1+IM) = 2200; liquidation E(1+IM)/(1+MM) = 2200/1.0025
        assert liq("short", "2000", "1", "10") == pytest.approx(D("2194.513716"), abs=D("1e-5"))
        assert bankruptcy_price(
            side="short", entry_price=D("2000"), quantity=D("1"), margin=D("200")
        ) == D("2200")

    def test_an_unleveraged_long_can_never_be_liquidated(self) -> None:
        """A 1x long has posted its whole notional, so it can only reach zero:
        no liquidation price, and no bankruptcy price either. This is what
        makes a 1x long exactly today's long-only position."""
        assert liq("long", "2000", "1", "1") is None
        assert (
            bankruptcy_price(side="long", entry_price=D("2000"), quantity=D("1"), margin=D("2000"))
            is None
        )

    def test_an_unleveraged_short_is_liquidated_near_double_the_entry_price(self) -> None:
        # A short's loss is unbounded, so even 1x has a liquidation price.
        assert liq("short", "2000", "1", "1") == pytest.approx(D("3990.024938"), abs=D("1e-5"))

    def test_liquidation_sits_between_entry_and_bankruptcy(self) -> None:
        for leverage in ("2", "5", "10", "50", "100"):
            long_liq = liq("long", "2000", "1", leverage)
            short_liq = liq("short", "2000", "1", leverage)
            assert long_liq is not None and short_liq is not None
            margin = initial_margin(notional=D("2000"), leverage=D(leverage))
            long_bk = bankruptcy_price(
                side="long", entry_price=D("2000"), quantity=D("1"), margin=margin
            )
            short_bk = bankruptcy_price(
                side="short", entry_price=D("2000"), quantity=D("1"), margin=margin
            )
            assert long_bk is not None and short_bk is not None
            assert long_bk < long_liq < D("2000") < short_liq < short_bk

    def test_higher_leverage_liquidates_closer_to_entry(self) -> None:
        distances = []
        for leverage in ("2", "5", "10", "20", "50"):
            price = liq("long", "2000", "1", leverage)
            assert price is not None
            distances.append(D("2000") - price)
        assert distances == sorted(distances, reverse=True)

    def test_the_default_5_percent_stop_is_only_reachable_below_about_19x(self) -> None:
        """Research doc finding: above ~19.1x leverage a 5% stop-loss can
        never fire before liquidation (ETHUSD margin parameters)."""
        stop_distance = D("0.05")
        for leverage, reachable in (("10", True), ("19", True), ("20", False), ("50", False)):
            price = liq("long", "2000", "1", leverage)
            assert price is not None
            distance = (D("2000") - price) / D("2000")
            assert (distance > stop_distance) is reachable, leverage


class TestLinearFormulaFollowsDeltasDefinition:
    """Delta: at the liquidation price, "Position Margin minus Unrealized PnL
    ... is equal to the Maintenance Margin"; at the bankruptcy price the loss
    equals the margin. The closed forms must satisfy exactly that. (This
    checks the algebra against the definition; it is not an independent
    confirmation of what Delta's own engine does.)"""

    @pytest.mark.parametrize("side", ["long", "short"])
    @pytest.mark.parametrize("leverage", ["1.5", "3", "7", "10", "25", "100", "200"])
    @pytest.mark.parametrize("entry", ["1850.25", "2600", "79000"])
    def test_margin_less_loss_equals_maintenance_margin_at_the_liquidation_price(
        self, side: str, leverage: str, entry: str
    ) -> None:
        qty = D("2")
        margin = initial_margin(notional=D(entry) * qty, leverage=D(leverage))
        price = liq(side, entry, "2", leverage)
        assert price is not None
        loss = -unrealized_pnl(
            side=side,  # type: ignore[arg-type]
            entry_price=D(entry),
            price=price,
            quantity=qty,
        )
        assert margin - loss == pytest.approx(MM * price * qty, rel=D("1e-12"))

    @pytest.mark.parametrize("side", ["long", "short"])
    @pytest.mark.parametrize("leverage", ["2", "10", "50"])
    def test_the_loss_equals_the_margin_at_the_bankruptcy_price(
        self, side: str, leverage: str
    ) -> None:
        qty = D("3")
        margin = initial_margin(notional=D("2000") * qty, leverage=D(leverage))
        price = bankruptcy_price(
            side=side,  # type: ignore[arg-type]
            entry_price=D("2000"),
            quantity=qty,
            margin=margin,
        )
        assert price is not None
        loss = -unrealized_pnl(
            side=side,  # type: ignore[arg-type]
            entry_price=D("2000"),
            price=price,
            quantity=qty,
        )
        assert loss == pytest.approx(margin, rel=D("1e-12"))

    def test_the_margin_form_reduces_to_the_leverage_closed_form(self) -> None:
        """Delta's page has no closed form; the engine's own is
        `E(1-IM)/(1-MM)` (long) and `E(1+IM)/(1+MM)` (short) with IM = 1/L."""
        entry, im = D("2000"), D("0.1")
        assert liq("long", "2000", "4", "10") == pytest.approx(
            entry * (1 - im) / (1 - MM), rel=D("1e-12")
        )
        assert liq("short", "2000", "4", "10") == pytest.approx(
            entry * (1 + im) / (1 + MM), rel=D("1e-12")
        )

    def test_less_margin_moves_the_liquidation_price_toward_the_market(self) -> None:
        """Funding taken from margin must tighten the liquidation price."""
        full = liquidation_price(
            side="long",
            entry_price=D("2000"),
            quantity=D("1"),
            margin=D("200"),
            maintenance_margin_rate=MM,
        )
        reduced = liquidation_price(
            side="long",
            entry_price=D("2000"),
            quantity=D("1"),
            margin=D("150"),
            maintenance_margin_rate=MM,
        )
        assert full is not None and reduced is not None
        assert reduced > full


class TestDeltaDocumentedExamples:
    """Step 1 of M3-E5-T2, as tests. Delta's liquidation guide has two worked
    examples (both for a BTCUSD contract sized so 20,000 contracts = 2 BTC at
    a 10,000 entry: an *inverse* contract, one contract = 1 USD). They are
    reproduced here with the inverse formulas; they do **not** match the
    linear formulas, which is exactly why they cannot verify them."""

    @staticmethod
    def inverse(entry: str, im: str, mm: str) -> tuple[Decimal, Decimal]:
        e, initial, maint = D(entry), D(im), D(mm)
        return e / (1 + initial), e / (1 + initial - maint)  # (bankruptcy, liquidation)

    def test_case_1_matches_the_inverse_formula(self) -> None:
        # Delta: long, entry 10,000, IM 1%, MM 0.5%: liquidation 9950, bankruptcy 9901.
        bankruptcy, liquidation = self.inverse("10000", "0.01", "0.005")
        assert bankruptcy == pytest.approx(D("9901"), abs=D("0.5"))
        assert liquidation == pytest.approx(D("9950"), abs=D("0.5"))

    def test_case_2_matches_the_inverse_formula(self) -> None:
        # Delta: long, entry 10,000, IM 3.25%, MM 1.63%: bankruptcy 9685.5. The
        # page prints the liquidation price as 9940.5, but the same example goes
        # on to say the partial-liquidation price is "1% away from the current
        # Mark Price of 9840", so 9840.5 is what it means (a typo on the page).
        bankruptcy, liquidation = self.inverse("10000", "0.0325", "0.0163")
        assert bankruptcy == pytest.approx(D("9685.5"), abs=D("0.5"))
        assert liquidation == pytest.approx(D("9840.5"), abs=D("0.5"))

    def test_the_linear_formula_does_not_reproduce_them_so_they_cannot_verify_it(self) -> None:
        """This is the point: at Case 2's 3.25% margin the linear bankruptcy
        price is 9675 against Delta's printed 9685.5, so the examples are not
        evidence for the linear formula in either direction."""
        margin = initial_margin(notional=D("10000"), leverage=D(1) / D("0.0325"))
        bankruptcy = bankruptcy_price(
            side="long", entry_price=D("10000"), quantity=D("1"), margin=margin
        )
        assert bankruptcy == pytest.approx(D("9675"), abs=D("0.01"))
        assert abs(bankruptcy - D("9685.5")) > D("10")  # type: ignore[operator]


class TestMaintenanceMarginBaseAmbiguityIsSmall:
    """One genuine ambiguity remains for the linear formula: whether the
    maintenance margin is taken on the liquidation price (used here) or the
    entry price. Bound how much it could matter."""

    @staticmethod
    def entry_based(side: str, entry: D, im: D) -> D:
        return entry * (1 - im + MM) if side == "long" else entry * (1 + im - MM)

    @pytest.mark.parametrize("leverage", ["5", "10", "20", "50", "100", "200"])
    @pytest.mark.parametrize("side", ["long", "short"])
    def test_at_5x_and_above_the_two_conventions_differ_by_under_a_twentieth_of_a_percent(
        self, side: str, leverage: str
    ) -> None:
        entry = D("2000")
        ours = liq(side, "2000", "1", leverage)
        assert ours is not None
        other = self.entry_based(side, entry, D(1) / D(leverage))
        assert abs(ours - other) / entry < D("0.0005")

    def test_it_is_largest_at_1x_where_a_long_cannot_be_liquidated_anyway(self) -> None:
        # At 1x the entry-based long liquidation would sit at 0.25% of entry
        # (a 99.75% fall); ours is "cannot be liquidated". Irrelevant in practice.
        assert self.entry_based("long", D("2000"), D(1)) == D("5")


class TestVerifiedLinearReference:
    """The slot that closes Step 1 for real. Read one figure from Delta's
    liquidation-price calculator for a *linear* contract (e.g. ETHUSD: enter a
    quantity, an entry price and a leverage; note the liquidation price it
    shows) and add it below. Until then this is skipped, on purpose."""

    VERIFIED_FIGURES: list[dict[str, str]] = []
    # Example shape once a figure is available:
    # {"side": "long", "entry": "2500", "quantity": "0.1", "leverage": "10", "liquidation": "..."}

    @pytest.mark.skipif(
        not VERIFIED_FIGURES,
        reason="no liquidation price from Delta for a linear contract has been added yet "
        "(see this class's docstring); the linear formula is derived, not verified",
    )
    def test_matches_a_real_delta_linear_liquidation_price(self) -> None:
        for figure in self.VERIFIED_FIGURES:
            computed = liq(figure["side"], figure["entry"], figure["quantity"], figure["leverage"])
            assert computed == pytest.approx(D(figure["liquidation"]), rel=D("0.0005"))


class TestLiquidationPredicates:
    def test_a_long_is_liquidated_at_or_below_and_a_short_at_or_above(self) -> None:
        assert is_liquidated(side="long", mark_price=D("1800"), liquidation=D("1804.5"))
        assert is_liquidated(side="long", mark_price=D("1804.5"), liquidation=D("1804.5"))
        assert not is_liquidated(side="long", mark_price=D("1805"), liquidation=D("1804.5"))
        assert is_liquidated(side="short", mark_price=D("2200"), liquidation=D("2194.5"))
        assert not is_liquidated(side="short", mark_price=D("2190"), liquidation=D("2194.5"))

    def test_a_position_with_no_liquidation_price_is_never_liquidated(self) -> None:
        assert not is_liquidated(side="long", mark_price=D("0.01"), liquidation=None)

    def test_gapping_past_the_bankruptcy_price_is_flagged(self) -> None:
        assert gapped_through_bankruptcy(side="long", mark_price=D("1790"), bankruptcy=D("1800"))
        assert not gapped_through_bankruptcy(
            side="long", mark_price=D("1800"), bankruptcy=D("1800")
        )
        assert gapped_through_bankruptcy(side="short", mark_price=D("2210"), bankruptcy=D("2200"))
        assert not gapped_through_bankruptcy(
            side="short", mark_price=D("2195"), bankruptcy=D("2200")
        )


class TestEffectiveLeverage:
    def test_is_notional_over_equity(self) -> None:
        assert effective_leverage(notional=D("30000"), equity=D("10000")) == D("3")

    def test_is_zero_when_there_is_no_equity(self) -> None:
        assert effective_leverage(notional=D("30000"), equity=D("0")) == D("0")


class TestFundingPayment:
    """`funding_rate` is a FRACTION here (0.0001 = 0.01%); the percent-to-
    fraction conversion happens once, at ingestion (see test_funding_rates)."""

    def test_longs_pay_when_the_rate_is_positive_and_shorts_receive(self) -> None:
        kwargs = {"quantity": D("10"), "index_price": D("2500"), "funding_rate": D("0.0001")}
        assert funding_payment(side="long", **kwargs) == D("2.5")  # 25,000 * 0.01%
        assert funding_payment(side="short", **kwargs) == D("-2.5")

    def test_shorts_pay_when_the_rate_is_negative_and_longs_receive(self) -> None:
        kwargs = {"quantity": D("10"), "index_price": D("2500"), "funding_rate": D("-0.0001")}
        assert funding_payment(side="long", **kwargs) == D("-2.5")
        assert funding_payment(side="short", **kwargs) == D("2.5")

    def test_it_is_priced_on_the_index_price_not_the_entry_price(self) -> None:
        cheap = funding_payment(
            side="long", quantity=D("1"), index_price=D("1000"), funding_rate=D("0.0002")
        )
        dear = funding_payment(
            side="long", quantity=D("1"), index_price=D("3000"), funding_rate=D("0.0002")
        )
        assert dear == cheap * 3
