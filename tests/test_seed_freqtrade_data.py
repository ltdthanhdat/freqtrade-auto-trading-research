import argparse

from scripts.seed_freqtrade_data import resolve_pairs


def test_smc_basket_preset_is_the_frozen_accepted_six_pair_basket():
    pairs = resolve_pairs(argparse.Namespace(pairs=None, preset="smc-basket"))

    assert pairs == [
        "PLAY/USDT:USDT",
        "BIO/USDT:USDT",
        "SPACE/USDT:USDT",
        "PENDLE/USDT:USDT",
        "BR/USDT:USDT",
        "YGG/USDT:USDT",
    ]
