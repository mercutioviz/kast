"""
Tests for stall detection logic in ZAPAPIClient.wait_for_plan_completion.

Stall detection is opt-in per job type: a job is only judged stalled if
_JOB_LIVENESS_PROBES maps its type to an endpoint that actually moves while
it runs. spiderAjax and spiderClient false-fired under the old exemption-list
shape because the automation-framework code path never updates the standalone
spider status endpoints, so both are mapped to None here — as is any job type
the taxonomy has never heard of, which is what test_unknown_job_type_no_stall
pins.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestStallDetection(unittest.TestCase):

    def _make_client(self):
        from kast.scripts.zap_api_client import ZAPAPIClient
        client = ZAPAPIClient.__new__(ZAPAPIClient)
        client.api_url = 'http://localhost:8080'
        client.api_key = 'test-key'
        client.timeout = 30
        client.debug = lambda msg: None
        client._write_progress_snapshot = MagicMock()
        client._try_cancel_plan = MagicMock()
        return client

    def _build_progress(self, info, finished=''):
        return {
            'planId': 0,
            'started': '2026-01-01T00:00:00Z',
            'finished': finished,
            'info': info,
            'warn': [],
            'error': [],
        }

    def test_spider_ajax_no_stall(self):
        """spiderAjax job sitting at 'started' across many cycles must not trigger stall."""
        client = self._make_client()

        # Simulate: spiderAjax starts and holds for 3 poll cycles, then completes.
        poll_responses = [
            self._build_progress([]),
            self._build_progress(['Job spiderAjax started']),
            self._build_progress(['Job spiderAjax started']),
            self._build_progress(['Job spiderAjax started']),
            self._build_progress(
                ['Job spiderAjax started', 'Job spiderAjax finished, time taken: 00:05:00'],
                finished='2026-01-01T00:05:01Z',
            ),
        ]

        with patch.object(client, '_make_request', side_effect=[
            p for p in poll_responses
        ]), patch('time.sleep'):
            success, progress = client.wait_for_plan_completion(
                plan_id=0, timeout=3600, poll_interval=30
            )

        self.assertTrue(success, "spiderAjax scan should complete successfully")
        client._try_cancel_plan.assert_not_called()

    def test_activescan_stall_fires(self):
        """activeScan stalled (ascan 100%, info frozen) must still trigger after 2 cycles."""
        client = self._make_client()

        # info frozen at 'Job activeScan started', ascan reports 100% (done but plan hung)
        frozen_progress = self._build_progress(['Job activeScan started'])

        ascan_done = {'status': '100'}

        call_count = {'n': 0}

        def make_request(endpoint, **kwargs):
            call_count['n'] += 1
            if 'planProgress' in endpoint:
                return frozen_progress
            if 'ascan/view/status' in endpoint:
                return ascan_done
            return {}

        with patch.object(client, '_make_request', side_effect=make_request), \
             patch('time.sleep'):
            success, progress = client.wait_for_plan_completion(
                plan_id=0, timeout=3600, poll_interval=30
            )

        self.assertFalse(success, "Stalled activeScan should abort after 2 cycles")
        client._try_cancel_plan.assert_called_once_with(0)

    def test_activescan_in_progress_no_stall(self):
        """activeScan still running (ascan < 100%) must not trigger stall."""
        client = self._make_client()

        frozen_progress = self._build_progress(['Job activeScan started'])

        # ascan running at 50%, then 80%, then plan finishes
        responses = [
            frozen_progress,  # poll 1 — info empty, no stall yet
            frozen_progress,  # poll 2 — info frozen, ascan at 50% → no stall
            frozen_progress,  # poll 3 — info frozen, ascan at 80% → no stall
            self._build_progress(
                ['Job activeScan started', 'Job activeScan finished'],
                finished='2026-01-01T00:10:00Z',
            ),
        ]
        ascan_responses = [{'status': '50'}, {'status': '80'}]
        ascan_iter = iter(ascan_responses)

        def make_request(endpoint, **kwargs):
            if 'planProgress' in endpoint:
                return responses.pop(0)
            if 'ascan/view/status' in endpoint:
                return next(ascan_iter, {'status': '100'})
            return {}

        with patch.object(client, '_make_request', side_effect=make_request), \
             patch('time.sleep'):
            success, progress = client.wait_for_plan_completion(
                plan_id=0, timeout=3600, poll_interval=30
            )

        self.assertTrue(success)
        client._try_cancel_plan.assert_not_called()

    def test_spider_client_no_stall(self):
        """spiderClient job sitting at 'started' must not trigger stall (same fix as spiderAjax)."""
        client = self._make_client()

        poll_responses = [
            self._build_progress([]),
            self._build_progress(['Job spiderClient started']),
            self._build_progress(['Job spiderClient started']),
            self._build_progress(['Job spiderClient started']),
            self._build_progress(
                ['Job spiderClient started', 'Job spiderClient finished, time taken: 00:02:00'],
                finished='2026-01-01T00:02:01Z',
            ),
        ]

        with patch.object(client, '_make_request', side_effect=[
            p for p in poll_responses
        ]), patch('time.sleep'):
            success, progress = client.wait_for_plan_completion(
                plan_id=0, timeout=3600, poll_interval=30
            )

        self.assertTrue(success, "spiderClient scan should complete successfully")
        client._try_cancel_plan.assert_not_called()

    def test_no_stall_when_info_grows(self):
        """Stall counter must reset whenever info list grows, regardless of job type."""
        client = self._make_client()

        responses = [
            self._build_progress([]),
            self._build_progress(['Job activeScan started']),
            self._build_progress(['Job activeScan started', 'Job activeScan finished'],
                                 finished='2026-01-01T00:01:00Z'),
        ]

        def make_request(endpoint, **kwargs):
            if 'planProgress' in endpoint:
                return responses.pop(0)
            return {}

        with patch.object(client, '_make_request', side_effect=make_request), \
             patch('time.sleep'):
            success, _ = client.wait_for_plan_completion(
                plan_id=0, timeout=3600, poll_interval=30
            )

        self.assertTrue(success)
        client._try_cancel_plan.assert_not_called()

    def test_unknown_job_type_no_stall(self):
        """A job type absent from the taxonomy must never trigger a stall abort.

        This is the regression that spiderAjax and then spiderClient each hit:
        an unmapped job type used to inherit the activeScan treatment, and with
        no active scan running ascan/view/status/ reports done, so a healthy
        long-running job was aborted mid-scan. The timeout still catches a real
        crash — just later, which is the safe direction to be wrong in.
        """
        client = self._make_client()

        frozen_progress = self._build_progress(['Job spiderQuantum started'])
        responses = [frozen_progress] * 4 + [
            self._build_progress(
                ['Job spiderQuantum started', 'Job spiderQuantum finished'],
                finished='2026-01-01T00:09:00Z',
            ),
        ]

        def make_request(endpoint, **kwargs):
            if 'planProgress' in endpoint:
                return responses.pop(0)
            # A job with no active scan behind it: ZAP reports the scanner idle.
            if 'ascan/view/status' in endpoint:
                return {'status': '100'}
            return {}

        with patch.object(client, '_make_request', side_effect=make_request), \
             patch('time.sleep'):
            success, _ = client.wait_for_plan_completion(
                plan_id=0, timeout=3600, poll_interval=30
            )

        self.assertTrue(success, "Unmapped job type must not be judged stalled")
        client._try_cancel_plan.assert_not_called()

    def test_started_job_type_parsing(self):
        """The job type comes from ZAP's own message, matched anchored."""
        from kast.scripts.zap_api_client import ZAPAPIClient

        parse = ZAPAPIClient._started_job_type
        self.assertEqual(parse('Job activeScan started'), 'activeScan')
        self.assertEqual(parse('  Job spiderAjax started  '), 'spiderAjax')
        self.assertIsNone(parse('Job activeScan finished, time taken: 00:05:00'))
        self.assertIsNone(parse('Job activeScan started scanning'))
        self.assertIsNone(parse(''))
        self.assertIsNone(parse(None))

    def test_taxonomy_covers_every_job_type_kast_emits(self):
        """Every job type kast puts in an automation plan must be classified.

        An unclassified type is safe (it just skips stall detection) but silent.
        Pinning it here means adding a job to a profile forces a deliberate
        answer about whether that job has a liveness signal.
        """
        import yaml

        from kast.scripts.zap_api_client import _JOB_LIVENESS_PROBES

        profile_dir = Path(__file__).resolve().parent.parent / 'config'
        plans = sorted(profile_dir.glob('zap_automation_*.yaml'))
        self.assertTrue(plans, f"No ZAP automation profiles found under {profile_dir}")

        emitted = set()
        for plan_path in plans:
            plan = yaml.safe_load(plan_path.read_text()) or {}
            for job in plan.get('jobs', []) or []:
                if job.get('type'):
                    emitted.add(job['type'])
        # _inject_spider_type swaps the 'spider' job for one of these at runtime.
        emitted.update({'spiderAjax', 'spiderClient'})

        missing = sorted(emitted - set(_JOB_LIVENESS_PROBES))
        self.assertEqual(
            missing, [],
            f"Job types in shipped ZAP profiles are absent from _JOB_LIVENESS_PROBES: {missing}"
        )


if __name__ == '__main__':
    unittest.main()
