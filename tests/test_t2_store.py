from serial_writer.models import CharacterState, Fact, StateDelta, Thread
from serial_writer.store import Store


def test_store_replay_and_idempotency(tmp_path):
    store = Store(run_dir=tmp_path)

    delta1 = StateDelta(
        ep_no=1,
        summary="Vance meets Maya.",
        characters_upserts=[CharacterState(name="Vance", status="alive", location="Metro Central")],
        new_facts=[Fact(text="Metro signal is glitched", subject="signal", valid_from_ep=1, source_ep=1)],
        threads_planted=[Thread(id="t1", description="Investigate glitch", planted_ep=1)],
    )

    store.save_draft(ep_no=1, text="Sample text ep 1", summary="Vance meets Maya.")
    store.approve(ep_no=1, delta=delta1)

    state1 = store.replay_state(up_to_ep=1)
    assert "Vance" in state1.characters
    assert state1.characters["Vance"].location == "Metro Central"
    assert len(state1.facts) == 1
    assert "t1" in state1.threads

    delta2 = StateDelta(
        ep_no=2,
        summary="Vance moves to Deep Vault.",
        characters_upserts=[CharacterState(name="Vance", status="alive", location="Deep Vault")],
        threads_resolved=["t1"],
    )

    store.save_draft(ep_no=2, text="Sample text ep 2", summary="Vance moves to Deep Vault.")
    store.approve(ep_no=2, delta=delta2)

    state2 = store.replay_state(up_to_ep=2)
    assert state2.characters["Vance"].location == "Deep Vault"
    assert state2.threads["t1"].status == "resolved"


def test_rejected_draft_leaves_state_clean(tmp_path):
    store = Store(run_dir=tmp_path)
    v = store.save_draft(ep_no=1, text="Unapproved text", summary="Draft summary")
    store.reject(ep_no=1, version=v)

    state = store.replay_state(up_to_ep=1)
    assert len(state.characters) == 0
    assert len(state.facts) == 0
