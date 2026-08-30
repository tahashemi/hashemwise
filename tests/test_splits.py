"""Splitting a total across people without ever losing a minor unit.

The invariant that matters: sum(shares) == total, exactly, for every input.
"""

import pytest

from src.money import (
    EmptyParticipants,
    NegativeShare,
    SplitMismatch,
    split_equal,
    validate_custom_split,
)


class TestSplitEqualExactness:
    @pytest.mark.parametrize("n", range(1, 51))
    @pytest.mark.parametrize("total", [1, 2, 3, 7, 100, 101, 999, 1000, 1234567, 10**12 + 7])
    def test_shares_always_sum_to_total(self, n, total):
        ids = list(range(1, n + 1))
        shares = split_equal(total, ids, payer_id=ids[0])
        assert sum(shares.values()) == total
        assert set(shares) == set(ids)

    @pytest.mark.parametrize("n", range(1, 51))
    @pytest.mark.parametrize("total", [1, 7, 100, 101, 999, 1234567])
    def test_shares_differ_by_at_most_one_minor_unit(self, n, total):
        ids = list(range(1, n + 1))
        shares = split_equal(total, ids, payer_id=ids[0])
        assert max(shares.values()) - min(shares.values()) <= 1

    def test_the_classic_hundred_by_three(self):
        # 100/3 in floats is 33.333... and loses a unit. Here it must not.
        shares = split_equal(100, [1, 2, 3], payer_id=1)
        assert sum(shares.values()) == 100
        assert sorted(shares.values()) == [33, 33, 34]

    def test_clean_division_gives_everyone_the_same(self):
        shares = split_equal(90, [1, 2, 3], payer_id=2)
        assert shares == {1: 30, 2: 30, 3: 30}

    def test_single_participant_takes_everything(self):
        assert split_equal(777, [5], payer_id=5) == {5: 777}


class TestRemainderGoesToPayerFirst:
    def test_payer_absorbs_the_leftover(self):
        # 100 across 3 people leaves 1 over; the payer eats it.
        shares = split_equal(100, [1, 2, 3], payer_id=2)
        assert shares[2] == 34
        assert shares[1] == 33 and shares[3] == 33

    def test_multiple_leftover_units_wrap_in_id_order_from_the_payer(self):
        # 101 across 3 leaves 2 over: payer (3) then wraps to the next id (1).
        shares = split_equal(101, [1, 2, 3], payer_id=3)
        assert shares == {3: 34, 1: 34, 2: 33}
        assert sum(shares.values()) == 101

    def test_payer_outside_the_participant_set_falls_back_to_lowest_id(self):
        # Someone can pay for a meal they did not eat.
        shares = split_equal(100, [2, 3, 4], payer_id=9)
        assert sum(shares.values()) == 100
        assert shares[2] == 34


class TestSplitEqualDeterminism:
    def test_participant_input_order_does_not_change_the_result(self):
        a = split_equal(1000, [3, 1, 2, 5, 4], payer_id=4)
        b = split_equal(1000, [5, 4, 3, 2, 1], payer_id=4)
        assert a == b

    def test_duplicate_ids_are_collapsed_not_double_counted(self):
        shares = split_equal(100, [1, 1, 2], payer_id=1)
        assert set(shares) == {1, 2}
        assert sum(shares.values()) == 100


class TestSplitEqualRejections:
    def test_empty_participants(self):
        with pytest.raises(EmptyParticipants):
            split_equal(100, [], payer_id=1)

    @pytest.mark.parametrize("total", [0, -1])
    def test_non_positive_total(self, total):
        with pytest.raises(ValueError):
            split_equal(total, [1, 2], payer_id=1)


class TestValidateCustomSplit:
    def test_exact_sum_passes(self):
        validate_custom_split(100, {1: 30, 2: 70})

    def test_under_reports_signed_delta(self):
        with pytest.raises(SplitMismatch) as e:
            validate_custom_split(100, {1: 30, 2: 60})
        assert e.value.delta == -10

    def test_over_reports_signed_delta(self):
        with pytest.raises(SplitMismatch) as e:
            validate_custom_split(100, {1: 30, 2: 80})
        assert e.value.delta == 10

    def test_zero_share_is_allowed(self):
        # A participant can be present but owe nothing.
        validate_custom_split(100, {1: 100, 2: 0})

    def test_negative_share_rejected(self):
        with pytest.raises(NegativeShare):
            validate_custom_split(100, {1: 110, 2: -10})

    def test_empty_rejected(self):
        with pytest.raises(EmptyParticipants):
            validate_custom_split(100, {})
