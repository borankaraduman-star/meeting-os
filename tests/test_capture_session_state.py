"""Session and channel recording state from synthetic capture-native.jsonl journals (tempfile only, no audio).
`started` proves only that startCapture returned; a channel is receiving once its first PCM buffer is journaled."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from meeting_os.desktop import capture_state

S, OLD = 'oturum-yeni', 'oturum-eski'


def line(event, session=S, launch=1, **extra):
    return {'event': event, 'session': session, 'launch': launch, **extra}


class SessionStateTests(unittest.TestCase):
    def state(self, events, raw_tail=''):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name)/'capture-native.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in events)+'\n'+raw_tail)
        return capture_state({'capture_dir': self.tmp.name})

    def test_started_without_pcm_is_awaiting_stream_and_both_channels_wait(self):
        wall = time.time()-7
        state = self.state([line('started', schema=2, epoch=0, wall=wall)])
        self.assertEqual((state['schema'], state['session'], state['session_state']), (2, S, 'awaiting_stream'))
        for source in ('mic', 'system'):
            self.assertEqual(state['channels'][source]['state'], 'awaiting_first_buffer')
            self.assertEqual(state['channels'][source]['epoch'], 0)
            self.assertGreaterEqual(state['channels'][source]['age_seconds'], 6)   # the app warns after 5 s; never an error
        self.assertEqual(state['state'], 'capturing')                              # the old key keeps its old meaning
        self.assertNotIn('message', state)

    def test_long_permission_wait_then_denied_never_receives_and_fails_in_turkish(self):
        asked = [line('permission', kind='screen_audio', state='requested', wall=time.time()-600)]
        waiting = self.state(asked)
        self.assertEqual(waiting['session_state'], 'awaiting_permission')         # ten minutes: still no timeout
        denied = self.state(asked+[line('permission', kind='screen_audio', state='denied')])
        self.assertEqual(denied['session_state'], 'failed')
        self.assertIn('izni verilmedi', denied['message']); self.assertIn('Sistem Ayarları', denied['message'])
        self.assertTrue(all(c['state'] == 'awaiting_first_buffer' for c in denied['channels'].values()))

    def test_silent_microphone_is_silent_not_stalled_while_system_has_signal(self):
        state = self.state([line('started', schema=2, epoch=0),
                            line('first_buffer', source='mic', epoch=0, seq=1, host_time=10.0, silent=True),
                            line('first_buffer', source='system', epoch=0, seq=1, host_time=10.1, silent=False)])
        self.assertEqual(state['channels']['mic']['state'], 'silent')
        self.assertEqual(state['channels']['system']['state'], 'signal')
        self.assertEqual(state['session_state'], 'receiving')

    def test_a_late_line_from_an_older_launch_or_session_changes_nothing(self):
        fresh = [line('started', launch=1, schema=2, epoch=0),
                 line('first_buffer', launch=1, source='mic', epoch=0, seq=1, silent=False),
                 {'event': 'relaunch', 'attempt': 1, 'reason': 'stall', 'start_offset': 12.0, 'session': S},
                 line('started', launch=2, schema=2, epoch=0),
                 line('first_buffer', launch=2, source='mic', epoch=0, seq=1, silent=False),
                 line('first_buffer', launch=2, source='system', epoch=0, seq=1, silent=False)]
        clean = self.state(fresh)
        late = self.state(fresh+[line('channel_flow', launch=1, source='mic', state='stalled', epoch=0, seq=9),
                                 line('stopped', launch=1),
                                 line('error', launch=1, message='eski yardımcı'),
                                 line('restarted', session=OLD, launch=7, epoch=3, attempt=1),
                                 line('channel_flow', session=OLD, launch=7, source='system', state='stalled', epoch=3, seq=2)])
        for key in ('state', 'session', 'session_state', 'restarts'):
            self.assertEqual(late.get(key), clean.get(key), key)
        self.assertEqual({k: v['state'] for k, v in late['channels'].items()}, {'mic': 'signal', 'system': 'signal'})
        self.assertEqual(late['relaunches'], 1)

    def test_stalled_then_restarted_then_first_buffer_is_signal_and_gap_seconds_survive(self):
        events = [line('started', schema=2, epoch=0),
                  line('first_buffer', source='mic', epoch=0, seq=1, silent=False),
                  line('chunk', source='mic', path='mic-000000.wav', start=0.0, duration=12.0),
                  line('channel_flow', source='mic', state='stalled', epoch=0, seq=2)]
        stalled = self.state(events)
        self.assertEqual(stalled['channels']['mic']['state'], 'stalled')
        events += [line('restarting', attempt=1, reason='silence'), line('restarted', attempt=1, epoch=1)]
        restarted = self.state(events)
        self.assertEqual(restarted['channels']['mic'], {**restarted['channels']['mic'], 'state': 'awaiting_first_buffer', 'epoch': 1})
        events += [line('gap', source='mic', start=12.0, end=20.5),
                   line('first_buffer', source='mic', epoch=1, seq=1, silent=False)]
        recovered = self.state(events)
        self.assertEqual((recovered['channels']['mic']['state'], recovered['channels']['mic']['epoch']), ('signal', 1))
        self.assertEqual((recovered['gap_seconds'], recovered['restarts']), (8.5, 1))
        self.assertEqual(recovered['session_state'], 'receiving')

    def test_a_stall_before_any_buffer_is_not_receiving_and_a_stall_after_buffers_still_is(self):
        """Review s3 #4: the helper's two-second stall timer runs from the stream's set-up, so `stalled` can be the
        first line a channel ever writes. That is no audio evidence: no 'receiving', no running clock."""
        wall = time.time()-3
        never = self.state([line('started', schema=2, epoch=0, wall=wall),
                            line('channel_flow', source='mic', state='stalled', epoch=0, seq=0),
                            line('channel_flow', source='system', state='stalled', epoch=0, seq=0)])
        self.assertEqual(never['session_state'], 'awaiting_stream')
        self.assertEqual({k: v['state'] for k, v in never['channels'].items()}, {'mic': 'awaiting_first_buffer', 'system': 'awaiting_first_buffer'})
        self.assertGreaterEqual(never['channels']['mic']['age_seconds'], 2)   # the app's five-second warning still dates from set-up
        # After a restart the buffer counter carries over (seq 7), so a stall in the new epoch proves nothing either.
        restarted = self.state([line('started', schema=2, epoch=0),
                                line('first_buffer', source='mic', epoch=0, seq=1, silent=False),
                                line('channel_flow', source='mic', state='signal', epoch=0, seq=1),
                                line('restarted', attempt=1, epoch=1),
                                line('channel_flow', source='mic', state='stalled', epoch=1, seq=7)])
        self.assertEqual((restarted['session_state'], restarted['channels']['mic']['state']), ('awaiting_stream', 'awaiting_first_buffer'))
        # Buffers, then flow changes, then a stall: the whole-journal reducer keeps the epoch's first_buffer next to
        # the newest flow line, so this channel reads stalled (it did deliver) and the session stays receiving.
        flowed = self.state([line('started', schema=2, epoch=0),
                             line('first_buffer', source='mic', epoch=0, seq=1, silent=False),
                             line('channel_flow', source='mic', state='signal', epoch=0, seq=1),
                             line('channel_flow', source='mic', state='silent', epoch=0, seq=4),
                             line('channel_flow', source='mic', state='stalled', epoch=0, seq=9)])
        self.assertEqual((flowed['session_state'], flowed['channels']['mic']['state']), ('receiving', 'stalled'))

    def test_schema_1_journal_is_unverified_and_keeps_every_old_key_identical(self):
        old = [{'event': 'started'}, {'event': 'chunk', 'source': 'mic', 'start': 0, 'duration': 12},
               {'event': 'restarted', 'attempt': 1}, {'event': 'wake', 'gap': 30.0},
               {'event': 'gap', 'source': 'mic', 'start': 12, 'end': 13}, {'event': 'chunk', 'source': 'system', 'start': 0, 'duration': 12}]
        state = self.state(old)
        self.assertEqual((state['schema'], state['session']), (1, None))
        self.assertEqual({k: v['state'] for k, v in state['channels'].items()}, {'mic': 'unverified', 'system': 'unverified'})
        self.assertEqual(state['session_state'], 'receiving')
        legacy = {'state': 'capturing', 'seconds': 12, 'sources': {'mic': 12, 'system': 12}, 'restarts': 1, 'wakes': 1,
                  'gap_seconds': 1.0, 'wake_gap_seconds': 30.0}
        self.assertEqual({k: state[k] for k in legacy}, legacy)
        self.assertNotIn('relaunches', state)
        self.assertEqual(self.state(old+[{'event': 'error', 'message': 'x'}])['state'], 'error')   # schema 1: unchanged

    def test_reversed_mic_and_system_lines_keep_the_timeline(self):
        ordered = [line('started', schema=2, epoch=0),
                   line('first_buffer', source='mic', epoch=0, seq=1, silent=False),
                   line('channel_flow', source='mic', state='silent', epoch=0, seq=2),
                   line('first_buffer', source='system', epoch=0, seq=1, silent=True),
                   line('channel_flow', source='system', state='signal', epoch=0, seq=2),
                   line('chunk', source='mic', start=0.0, duration=12.0), line('chunk', source='system', start=0.0, duration=12.0),
                   line('chunk', source='mic', start=12.0, duration=12.0)]
        forward = self.state(ordered)
        backward = self.state(ordered[:1]+list(reversed(ordered[1:])))
        for key in ('sources', 'seconds', 'session_state'):
            self.assertEqual(backward[key], forward[key], key)
        self.assertEqual({k: v['state'] for k, v in backward['channels'].items()}, {'mic': 'silent', 'system': 'signal'})
        self.assertEqual(forward['sources'], {'mic': 24.0, 'system': 12.0})

    def test_one_channel_failing_to_start_does_not_fail_the_other(self):
        state = self.state([line('started', schema=2, epoch=0),
                            line('error', source='mic', message='mic device gone'),
                            line('first_buffer', source='system', epoch=0, seq=1, silent=False)])
        self.assertEqual(state['channels']['system']['state'], 'signal')
        self.assertNotIn('error', state['channels']['system'])
        self.assertEqual(state['channels']['mic']['state'], 'awaiting_first_buffer')
        self.assertIn('Mikrofon', state['channels']['mic']['error'])
        self.assertEqual((state['session_state'], state['state']), ('receiving', 'capturing'))
        whole = self.state([line('started', schema=2, epoch=0), line('error', message='stream gone')])
        self.assertEqual((whole['session_state'], whole['state']), ('failed', 'error'))
        self.assertTrue(whole['message'])

    def test_missing_journal_keeps_old_shape_and_waits(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = capture_state({'capture_dir': tmp})
        self.assertEqual({k: state[k] for k in ('state', 'seconds', 'sources')}, {'state': 'waiting', 'seconds': 0, 'sources': {}})
        self.assertEqual(state['session_state'], 'awaiting_stream')

    def test_no_audio_or_text_is_read_and_the_journal_is_not_written(self):
        events = [line('started', schema=2, epoch=0), line('first_buffer', source='mic', epoch=0, seq=1, silent=False),
                  line('chunk', source='mic', path='/yok/mic-000000.wav', start=0.0, duration=12.0)]
        self.state(events)
        path = Path(self.tmp.name)/'capture-native.jsonl'; before = path.read_bytes()
        capture_state({'capture_dir': self.tmp.name})
        self.assertEqual(path.read_bytes(), before)


class CounterSessionTests(unittest.TestCase):
    def test_counters_skip_another_sessions_lines_but_keep_unstamped_ones(self):
        from meeting_os.capture_metrics import capture_health, journal_counters
        events = [line('restarted', epoch=1), line('restarted', session=OLD, epoch=1), {'event': 'relaunch', 'attempt': 1},
                  {'event': 'wake', 'gap': 4.0}]
        self.assertEqual(capture_health(events, S)['restarts'], 1)
        self.assertEqual(capture_health(events)['restarts'], 2)   # no session given: the old whole-journal count
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'j.jsonl'; path.write_text('\n'.join(json.dumps(e) for e in events))
            counted = journal_counters(path, S)
            self.assertEqual((counted['restarts'], counted['relaunches'], counted['wakes']), (1, 1, 1))



class WholeJournalStateTests(unittest.TestCase):
    """Audit 2026-10-16: the state came from the last 64 KB only. A steady signal or a steady silence writes no
    further transitions, so after ~30 minutes of chunk lines the first_buffer fell out and the channel read
    'awaiting_first_buffer' while it was recording."""
    def journal(self, events):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name)/'capture-native.jsonl'
        path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        return path

    def long_meeting(self, chunks=1500, sources=('mic', 'system')):
        now = time.time()
        events = [line('started', schema=2, epoch=0, wall=now-chunks*12),
                  line('first_buffer', source='mic', epoch=0, seq=1, silent=True, wall=now-chunks*12+1),
                  line('first_buffer', source='system', epoch=0, seq=1, silent=False, wall=now-chunks*12+1),
                  line('channel_flow', source='system', state='signal', epoch=0, seq=1)]
        for n in range(chunks):
            for source in sources:
                events.append(line('chunk', source=source, path=f'/kayit/{source}-{n:06d}.wav', start=12.0*n, duration=12.0, wall=now-(chunks-n)*12+12))
        return events

    def test_a_steady_channel_keeps_its_state_after_hours_of_chunk_lines(self):
        from meeting_os.capture_metrics import JOURNAL_TAIL_BYTES, journal_events, session_view
        events = self.long_meeting(); path = self.journal(events)
        self.assertGreater(path.stat().st_size, 4*JOURNAL_TAIL_BYTES)
        self.assertEqual(session_view(journal_events(path))['channels']['mic']['state'], 'awaiting_first_buffer')   # the old tail read
        state = capture_state({'capture_dir': str(path.parent)})
        self.assertEqual({k: v['state'] for k, v in state['channels'].items()}, {'mic': 'silent', 'system': 'signal'})
        self.assertEqual((state['session_state'], state['sources']), ('receiving', {'mic': 18000.0, 'system': 18000.0}))
        full = session_view(events)   # every line parsed: the folded journal must say exactly the same
        self.assertEqual({k: v['state'] for k, v in full['channels'].items()}, {k: v['state'] for k, v in state['channels'].items()})
        self.assertEqual(full['session_state'], state['session_state'])

    def test_polls_read_only_what_was_appended_and_a_rewritten_file_starts_over(self):
        from meeting_os import capture_metrics as M
        path = self.journal(self.long_meeting(chunks=600))
        meta = {'capture_dir': str(path.parent)}
        self.assertEqual(capture_state(meta)['channels']['mic']['state'], 'silent')
        offset = M._REDUCERS[str(path)].offset
        with path.open('a') as f: f.write(json.dumps(line('channel_flow', source='mic', state='stalled', epoch=0, seq=2))+'\n')
        self.assertEqual(capture_state(meta)['channels']['mic']['state'], 'stalled')
        self.assertGreater(M._REDUCERS[str(path)].offset, offset)
        # Same path, new and longer content: the saved offset no longer lines up, so nothing of the old file survives.
        path.write_text(''.join(json.dumps(e)+'\n' for e in [line('started', schema=2, epoch=0), line('first_buffer', source='system', epoch=0, seq=1, silent=False)]
                                + [line('chunk', source='system', path=f'/b/{n}.wav', start=12.0*n, duration=12.0) for n in range(900)]))
        state = capture_state(meta)
        self.assertEqual({k: v['state'] for k, v in state['channels'].items()}, {'mic': 'awaiting_first_buffer', 'system': 'signal'})
        self.assertEqual(state['sources'], {'system': 10800.0})


if __name__ == '__main__':
    unittest.main()
