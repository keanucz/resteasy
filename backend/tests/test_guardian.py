"""Guardian: plain-code checks on every action before it reaches a device, a speaker or a phone
(coord/AGENT_FLOW.md section 5). Each check returns a Verdict; a blocked action may carry a safe
replacement so the night never goes quiet."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.guardian import Guardian, GuardianConfig, Verdict
from app.agents.night_watch import Alert, Command, Say

TZ = ZoneInfo("America/Los_Angeles")
NIGHT = datetime(2026, 10, 25, 3, 0, tzinfo=TZ).timestamp()
DAY = datetime(2026, 10, 24, 13, 0, tzinfo=TZ).timestamp()


def guardian(**kw):
    return Guardian(GuardianConfig(timezone="America/Los_Angeles", **kw))


# ---------- device commands ----------


def test_night_brightness_is_capped_not_blocked():
    g = guardian()
    v = g.check(Command("mum", "set_light", {"brightness_pct": 80, "color": "warm", "fade_s": 3}), NIGHT)
    assert v.allowed is False and "40" in v.reason
    assert v.replacement == Command("mum", "set_light", {"brightness_pct": 40, "color": "warm", "fade_s": 3})


def test_daytime_brightness_is_fine():
    bright = Command("mum", "set_light", {"brightness_pct": 80, "color": "warm", "fade_s": 3})
    v = guardian().check(bright, DAY)
    assert v == Verdict(True)


def test_pulse_outside_4_to_14_bpm_is_blocked():
    v = guardian().check(Command("mum", "pulse", {"start_bpm": 20, "end_bpm": 6, "duration_min": 10}), NIGHT)
    assert not v.allowed and v.replacement is None
    ok = guardian().check(Command("mum", "pulse", {"start_bpm": 12, "end_bpm": 6, "duration_min": 10}), NIGHT)
    assert ok.allowed


def test_unknown_command_is_blocked():
    v = guardian().check(Command("mum", "unlock_door", {}), NIGHT)
    assert not v.allowed


def test_vibrate_repeat_is_clamped():
    v = guardian().check(Command("mum", "vibrate", {"pattern": "tap", "repeat": 9}), NIGHT)
    assert not v.allowed and v.replacement.args["repeat"] == 5


# ---------- words ----------


def test_medical_claims_in_a_family_message_are_blocked_and_rewritten():
    g = guardian()
    drafted = Alert("Sarah", "sms", "Mum got up at 03:00 and hasn't come back. She might have had a stroke.")
    v = g.check(drafted, NIGHT)
    assert not v.allowed and "stroke" in v.reason
    assert isinstance(v.replacement, Alert)
    assert "stroke" not in v.replacement.message
    assert v.replacement.contact == "Sarah" and v.replacement.channel == "sms"


def test_medical_words_in_a_spoken_line_are_blocked():
    v = guardian().check(Say("You may be having a heart attack, stay still."), NIGHT)
    assert not v.allowed and v.replacement == Say(Guardian.SAFE_SAY)


def test_plain_message_passes():
    plain = Alert("Sarah", "sms", "Mum got up at 03:00 and hasn't come back (25 min). She didn't answer.")
    v = guardian().check(plain, NIGHT)
    assert v == Verdict(True)


def test_sms_to_a_contact_without_consent_is_blocked():
    g = guardian(sms_consent={"Sarah": False})
    v = g.check(Alert("Sarah", "sms", "Heads-up."), NIGHT)
    assert not v.allowed and "consent" in v.reason
    assert g.check(Alert("Sarah", "app", "Heads-up."), NIGHT).allowed


# ---------- alert volume ----------


def test_too_many_alerts_to_one_contact_in_a_night_are_blocked():
    g = guardian(max_alerts_per_contact=3)
    for i in range(3):
        assert g.check(Alert("Sarah", "sms", f"msg {i}"), NIGHT + i * 600).allowed
    v = g.check(Alert("Sarah", "sms", "msg 4"), NIGHT + 1800)
    assert not v.allowed and "3" in v.reason
    assert g.check(Alert("Tom", "sms", "msg"), NIGHT + 1800).allowed  # per contact, not global


def test_alert_count_resets_the_next_night():
    g = guardian(max_alerts_per_contact=1)
    assert g.check(Alert("Sarah", "sms", "a"), NIGHT).allowed
    assert not g.check(Alert("Sarah", "sms", "b"), NIGHT + 60).allowed
    assert g.check(Alert("Sarah", "sms", "c"), NIGHT + 24 * 3600).allowed


def test_a_repeat_of_the_same_alert_inside_the_step_wait_is_blocked():
    g = guardian(step_wait_min=2)
    assert g.check(Alert("Sarah", "call", "x"), NIGHT).allowed
    v = g.check(Alert("Sarah", "call", "x"), NIGHT + 30)
    assert not v.allowed and "2 min" in v.reason
    assert g.check(Alert("Sarah", "call", "x"), NIGHT + 121).allowed


# ---------- config changes (Morning Brief) ----------


def test_config_diff_keeps_only_whitelisted_keys_within_bounds():
    g = guardian()
    diff = {"checkin_timeout_min": 45, "quiet_start": "23:00", "voice_id": "x", "path_light_pct": 30}
    v = g.check_config(diff)
    assert not v.allowed
    assert v.replacement == {"checkin_timeout_min": 30, "quiet_start": "23:00", "path_light_pct": 30}
    assert "voice_id" in v.reason and "checkin_timeout_min" in v.reason


def test_a_clean_config_diff_is_allowed_unchanged():
    v = guardian().check_config({"checkin_timeout_min": 15})
    assert v == Verdict(True)


# ---------- screening a batch ----------


def test_screen_returns_what_to_run_with_each_verdict():
    g = guardian()
    actions = [
        Command("mum", "set_light", {"brightness_pct": 80, "color": "warm", "fade_s": 3}),
        Say("The light's on."),
        Alert("Sarah", "sms", "She may have had a stroke. Please check."),
        Command("mum", "pulse", {"start_bpm": 40, "end_bpm": 6, "duration_min": 10}),
    ]
    screened = g.screen(actions, NIGHT)
    assert [s.run is not None for s in screened] == [True, True, True, False]
    assert screened[0].run.args["brightness_pct"] == 40 and not screened[0].verdict.allowed
    assert screened[1].run is actions[1] and screened[1].verdict.allowed
    assert screened[2].run.message == "Please check." and screened[2].original is actions[2]
    assert screened[3].run is None and not screened[3].verdict.allowed


def test_free_text_for_her_is_checked_too():
    assert guardian().check_text("Night night Gran, love you.").allowed
    assert not guardian().check_text("Take another tablet if your chest hurts.").allowed


def test_her_own_quoted_words_are_not_a_medical_claim():
    """She said it, the agent only reports it; family should hear her words."""
    quoted = Alert("Sarah", "sms", 'Mum got up at 03:00 and hasn\'t come back (25 min). '
                                   'She said: "I think I\'ve had a stroke".')
    assert guardian().check(quoted, NIGHT).allowed
    paraphrased = Alert("Sarah", "sms", "Mum got up at 03:00. She thinks she has had a stroke.")
    assert not guardian().check(paraphrased, NIGHT).allowed
