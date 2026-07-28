"""
Tests for stall detection logic in ZAPAPIClient.wait_for_plan_completion.

Covers the spiderAjax false-positive fix: when the last planProgress.info
message is "Job spiderAjax started", stall detection must not fire because
the automation-framework code path never updates ajaxSpider/view/status/.
"""

import time
import unittest
from unittest.mock import MagicMock, call, patch


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


if __name__ == '__main__':
    unittest.main()
