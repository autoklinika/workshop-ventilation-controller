import unittest

from ventilation_core.domain.models import FanSetpoints
from ventilation_core.domain.policy import FanSetpointPolicy, SetpointValidationError


class FanSetpointPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = FanSetpointPolicy(1.0, 10.0)

    def test_accepts_stop_and_operating_range(self) -> None:
        self.assertEqual(self.policy.validate_voltage(0), 0.0)
        self.assertEqual(self.policy.validate_voltage(1), 1.0)
        self.assertEqual(self.policy.validate_voltage(10), 10.0)

    def test_rejects_dead_band_and_out_of_range(self) -> None:
        for value in (-1, 0.5, 10.1):
            with self.subTest(value=value):
                with self.assertRaises(SetpointValidationError):
                    self.policy.validate_voltage(value)

    def test_validates_both_channels(self) -> None:
        self.assertEqual(
            self.policy.validate(FanSetpoints(2, 3)),
            FanSetpoints(2.0, 3.0),
        )
