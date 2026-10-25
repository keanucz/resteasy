-- The alert simulator only plays on pillows the test account OWNS. A test account can now also be a
-- contact in someone else's household (to try switching between people in the app), and playing
-- alerts there would write into a real pillow's night.

create or replace function public.simulate_alert(p_pillow text, p_level text) returns text
language plpgsql volatile security definer set search_path = public as $$
declare
    v_resident  uuid;
    v_name      text;
    v_now       timestamptz := now();
    v_incident  bigint;
    v_first     record;
    v_tag       jsonb := jsonb_build_object('simulated', true);
begin
    if not public.am_i_test() then
        raise exception 'Only test accounts can simulate alerts' using errcode = '42501';
    end if;

    select p.resident_id, r.preferred_name into v_resident, v_name
    from pillows p join residents r on r.id = p.resident_id
    where p.id = p_pillow
      and exists (select 1 from resident_contacts rc join contacts c on c.id = rc.contact_id
                  where rc.resident_id = p.resident_id and rc.role = 'owner' and c.user_id = (select auth.uid()));
    if v_resident is null then
        raise exception 'Alerts can only be played on a pillow you own' using errcode = '42501';
    end if;

    select c.id, c.full_name into v_first
    from resident_contacts rc join contacts c on c.id = rc.contact_id
    where rc.resident_id = v_resident order by rc.priority limit 1;

    case p_level
    when 'up' then
        insert into events (pillow_id, event_type, device_ts, data) values (p_pillow, 'bed_exit', v_now, v_tag);
        update pillow_state set night_state = 'up', state_since = v_now, head_on = false, last_seen_at = v_now + interval '3 days'
        where pillow_id = p_pillow;
        return v_name || ' is out of bed.';

    when 'checkin' then
        insert into events (pillow_id, event_type, device_ts, data) values (p_pillow, 'checkin_start', v_now, v_tag);
        update pillow_state set night_state = 'check_in', state_since = v_now, last_seen_at = v_now + interval '3 days'
        where pillow_id = p_pillow;
        return 'The pillow is checking in with ' || v_name || '.';

    when 'alert_first' then
        insert into events (pillow_id, event_type, device_ts, data) values (p_pillow, 'checkin_timeout', v_now, v_tag);
        update pillow_state set night_state = 'escalating', state_since = v_now, last_seen_at = v_now + interval '3 days'
        where pillow_id = p_pillow;
        insert into incidents (pillow_id, kind, status, step, opened_at, summary)
        values (p_pillow, 'no_return', 'open', 1, v_now,
                v_name || ' got up and didn''t answer the pillow. ' || coalesce(v_first.full_name, 'The first contact') || ' was alerted.')
        returning id into v_incident;
        if v_first.id is not null then
            insert into notifications (incident_id, contact_id, channel) values (v_incident, v_first.id, 'app');
        end if;
        return coalesce(v_first.full_name, 'The first contact') || ' was alerted.';

    when 'alert_everyone' then
        select id into v_incident from incidents
        where pillow_id = p_pillow and kind = 'no_return' and status in ('open', 'acknowledged')
        order by opened_at desc limit 1;
        if v_incident is null then
            raise exception 'Start with "first contact alerted"' using errcode = 'P0001';
        end if;
        update incidents set step = 2,
            summary = v_name || ' got up and didn''t answer the pillow. Nobody answered the first alert, so everyone was alerted.'
        where id = v_incident;
        insert into notifications (incident_id, contact_id, channel)
        select v_incident, rc.contact_id, ch
        from resident_contacts rc, unnest(array['sms', 'call']) as ch
        where rc.resident_id = v_resident;
        return 'Everyone in the care circle was alerted.';

    when 'cold' then
        insert into incidents (pillow_id, kind, status, step, opened_at, summary)
        values (p_pillow, 'room_cold', 'open', 1, v_now, v_name || '''s bedroom is 15.2' || chr(176) || 'C. The pillow asked if the heating is on.');
        update pillow_state set temp_c = 15.2, last_seen_at = v_now + interval '3 days' where pillow_id = p_pillow;
        return 'The bedroom is cold.';

    when 'clear' then
        update incidents set status = 'resolved', resolved_at = v_now
        where pillow_id = p_pillow and status in ('open', 'acknowledged');
        insert into events (pillow_id, event_type, device_ts, data) values (p_pillow, 'bed_return', v_now, v_tag);
        update pillow_state set night_state = 'in_bed', state_since = v_now, head_on = true, temp_c = 19.5,
                                last_seen_at = v_now + interval '3 days'
        where pillow_id = p_pillow;
        return v_name || ' is back in bed. Alerts cleared.';

    else
        raise exception 'Unknown level %', p_level using errcode = '22023';
    end case;
end;
$$;
