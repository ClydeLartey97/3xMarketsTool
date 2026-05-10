from __future__ import annotations

from app.services.deep_hedger import evaluate_policy_cvar, train_policy


def test_trained_policy_beats_random_hedge_on_held_out_scenarios(tmp_path) -> None:
    model_path = tmp_path / "deep_hedger.pt"
    policy = train_policy(
        n_scenarios=512,
        epochs=8,
        batch_size=128,
        seed=13,
        output_path=model_path,
    )

    policy_cvar = evaluate_policy_cvar(policy, n_scenarios=512, seed=31)
    random_cvar = evaluate_policy_cvar(policy, n_scenarios=512, seed=31, random_hedge=True)

    assert model_path.exists()
    assert policy_cvar < random_cvar
