import unittest

from ventilation_core.domain.tacho import RPM_PER_HZ, TachoEstimator


class TachoEstimatorTests(unittest.TestCase):
    def test_validated_conversion_is_twenty_rpm_per_hz(self) -> None:
        self.assertEqual(RPM_PER_HZ, 20.0)

    def test_113_28_hz_matches_measured_full_speed(self) -> None:
        estimator = TachoEstimator(averaging_periods=4, timeout_seconds=0.25)
        period = 1.0 / 113.28
        now = 10.0
        estimator.add_edge(now)
        for _ in range(4):
            now += period
            reading = estimator.add_edge(now)

        self.assertTrue(reading.valid)
        self.assertAlmostEqual(reading.frequency_hz, 113.28, places=6)
        self.assertAlmostEqual(reading.rpm, 2265.6, places=5)
        self.assertEqual(reading.sample_count, 4)

    def test_19_933_hz_matches_measured_low_speed(self) -> None:
        estimator = TachoEstimator(averaging_periods=3, timeout_seconds=0.25)
        period = 1.0 / 19.933
        now = 1.0
        estimator.add_edge(now)
        for _ in range(3):
            now += period
            reading = estimator.add_edge(now)

        self.assertTrue(reading.valid)
        self.assertAlmostEqual(reading.rpm, 398.66, places=2)

    def test_timeout_reports_zero_and_invalid(self) -> None:
        estimator = TachoEstimator(timeout_seconds=0.25)
        estimator.add_edge(1.0)
        estimator.add_edge(1.01)

        reading = estimator.read(1.30)

        self.assertFalse(reading.valid)
        self.assertEqual(reading.frequency_hz, 0.0)
        self.assertEqual(reading.rpm, 0.0)

    def test_period_average_suppresses_single_edge_jitter(self) -> None:
        estimator = TachoEstimator(averaging_periods=4, timeout_seconds=0.25)
        estimator.add_edge(0.0)
        estimator.add_edge(0.010)
        estimator.add_edge(0.020)
        estimator.add_edge(0.031)
        reading = estimator.add_edge(0.040)

        self.assertTrue(reading.valid)
        self.assertAlmostEqual(reading.frequency_hz, 100.0, places=6)
        self.assertAlmostEqual(reading.rpm, 2000.0, places=5)

    def test_rejects_non_monotonic_timestamps(self) -> None:
        estimator = TachoEstimator()
        estimator.add_edge(2.0)
        with self.assertRaises(ValueError):
            estimator.add_edge(2.0)


if __name__ == "__main__":
    unittest.main()
