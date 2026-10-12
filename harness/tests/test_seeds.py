from matchlab.seeds import derive_seed, match_seeds, team_seed


def test_fixed_values():
    assert match_seeds(42, 2) == [737161366, 1416715386]
    assert team_seed(737161366, "left") == 1608858898
    assert team_seed(737161366, "right") == 308656577


def test_range_and_stability():
    seeds = match_seeds(7, 50)
    assert seeds == match_seeds(7, 50)
    assert all(0 <= s <= 0x7FFFFFFF for s in seeds)
    assert len(set(seeds)) == 50
    assert derive_seed("a", 1) != derive_seed("a", 2)
