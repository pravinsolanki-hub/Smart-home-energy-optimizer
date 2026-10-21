from datetime import datetime
from typing import Dict, List, Optional, Any
from app.models.schemas import DeviceState, DeviceType, ActionStatus

class DeviceManagerService:
    def __init__(self):
        # Initial device fleet states (simulating AWS IoT Core Device Shadows)
        self.devices: Dict[str, DeviceState] = {
            "thermostat_main": DeviceState(
                device_id="thermostat_main",
                name="Main Floor Smart Thermostat",
                device_type=DeviceType.THERMOSTAT,
                reported_state={"current_temp_f": 72.0, "mode": "cool", "fan": "auto", "setpoint_f": 72.0},
                desired_state={"setpoint_f": 72.0, "mode": "cool"},
                manual_override=False,
                last_updated=datetime.utcnow()
            ),
            "ev_charger_level2": DeviceState(
                device_id="ev_charger_level2",
                name="Level 2 Smart EV Charger",
                device_type=DeviceType.EV_CHARGER,
                reported_state={"connected": True, "charging": False, "kwh_delivered": 0.0, "max_amps": 32},
                desired_state={"charging": False, "scheduled_start": None},
                manual_override=False,
                last_updated=datetime.utcnow()
            ),
            "heat_pump_water_heater": DeviceState(
                device_id="heat_pump_water_heater",
                name="Smart Heat Pump Water Heater",
                device_type=DeviceType.HEAT_PUMP,
                reported_state={"water_temp_f": 125.0, "mode": "hybrid", "power_draw_kw": 0.45},
                desired_state={"mode": "hybrid", "temp_setpoint_f": 125.0},
                manual_override=False,
                last_updated=datetime.utcnow()
            )
        }
        self.action_history: Dict[str, Dict[str, Any]] = {}

    def get_all_devices(self) -> List[DeviceState]:
        return list(self.devices.values())

    def get_device(self, device_id: str) -> Optional[DeviceState]:
        return self.devices.get(device_id)

    def apply_action(self, action_id: str, device_id: str, desired_state: Dict[str, Any]) -> bool:
        """
        Applies an approved optimization action to the device shadow.
        Only executes if device does not have an active manual override.
        """
        device = self.devices.get(device_id)
        if not device:
            return False

        if device.manual_override:
            # Respect manual override - do not overwrite
            return False

        # Update desired state (simulating AWS IoT Device Shadow update)
        device.desired_state.update(desired_state)
        # In simulation, reported state tracks desired state after actuation
        device.reported_state.update(desired_state)
        device.last_updated = datetime.utcnow()

        self.action_history[action_id] = {
            "action_id": action_id,
            "device_id": device_id,
            "status": ActionStatus.APPROVED,
            "applied_at": datetime.utcnow().isoformat(),
            "applied_state": desired_state
        }
        return True

    def set_manual_override(self, device_id: str, state_update: Dict[str, Any]) -> bool:
        """
        Allows occupant to immediately override automation.
        Locks out automated updates until override is explicitly cleared.
        """
        device = self.devices.get(device_id)
        if not device:
            return False

        device.manual_override = True
        device.desired_state.update(state_update)
        device.reported_state.update(state_update)
        device.last_updated = datetime.utcnow()
        return True

    def clear_manual_override(self, device_id: str) -> bool:
        device = self.devices.get(device_id)
        if not device:
            return False
        device.manual_override = False
        device.last_updated = datetime.utcnow()
        return True
