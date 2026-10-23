# -*- mode: python; indent-tabs-mode: nil -*-

# PYTHONPATH=. python3 test/identity_test.py

import unittest

from mlat import identity

MILAN = (45.4642, 9.19, 120.0)


class PlaceholderUuid(unittest.TestCase):
    def test_sample_env_and_empty_values_are_placeholders(self):
        for u in ('XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX', 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
                  '00000000-0000-0000-0000-000000000000', '', ' - '):
            self.assertTrue(identity.is_placeholder_uuid(u), u)

    def test_real_and_malformed_but_unique_uuids_are_kept(self):
        # The malformed ones are all seen live on 2026-10-23: each is one receiver.
        for u in ('6a9423e0-7ba6-4672-81a4-81b715ac1ad2', '<28710a05-d56e-4ca1-8b1b-12f6d88d2c0f',
                  'b2a3a57040f17a3d', '8b61417e-a3eb-4407-b333-e1fe19568c0',
                  '3f9c‑a1b2‑4d5e‑7f90‑123456789abc'):
            self.assertFalse(identity.is_placeholder_uuid(u), u)

    def test_non_strings_are_left_alone(self):
        # Some clients send a list with one uuid: not a placeholder, and the
        # rest of the server already copes with it.
        self.assertFalse(identity.is_placeholder_uuid(['6a9423e0-7ba6-4672-81a4-81b715ac1ad2']))
        self.assertFalse(identity.is_placeholder_uuid(None))


class SameReceiver(unittest.TestCase):
    def test_uuids_decide_when_there_is_one(self):
        u = '6a9423e0-7ba6-4672-81a4-81b715ac1ad2'
        self.assertTrue(identity.same_receiver(u, MILAN, u, (48.1, 11.5, 500)))
        self.assertFalse(identity.same_receiver(u, MILAN, 'b2a3a57040f17a3d', MILAN))
        self.assertFalse(identity.same_receiver(u, MILAN, None, MILAN))
        self.assertFalse(identity.same_receiver(None, MILAN, u, MILAN))
        lst = ['6a9423e0-7ba6-4672-81a4-81b715ac1ad2']
        self.assertTrue(identity.same_receiver(lst, MILAN, list(lst), MILAN))

    def test_without_uuids_the_place_decides(self):
        self.assertTrue(identity.same_receiver(None, MILAN, None, (45.4646, 9.1905, 130.0)))
        # Two my_feeder_name stations in different towns are two receivers.
        self.assertFalse(identity.same_receiver(None, MILAN, None, (45.07, 7.69, 240.0)))

    def test_distance(self):
        self.assertAlmostEqual(identity.distance_m(MILAN, (45.07, 7.69, 0)) / 1000, 125.5, delta=1.5)
        self.assertEqual(identity.distance_m(MILAN, MILAN), 0.0)


class Live(unittest.TestCase):
    def test_live_means_heard_from_recently(self):
        self.assertTrue(identity.is_live(1000.0, 1000.0 + identity.LIVE_S - 1))
        self.assertFalse(identity.is_live(1000.0, 1000.0 + identity.LIVE_S + 1))
        self.assertFalse(identity.is_live(None, 1000.0))


if __name__ == '__main__':
    unittest.main()
