class ScenarioAnalyzer:
    def __init__(self, max_wait_time=300, max_person_time=600, person_without_car_delay=60):
        self.person_without_car_delay = person_without_car_delay
        self.max_wait_time = max_wait_time
        self.max_person_time = max_person_time
        self.person_without_car_start_time = None
        self.person_without_car_alerted = False
        self.car_present = False
        self.person_present = False
        self.car_appearance_time = None
        self.person_appearance_time = None
        self.car_abandoned_alerted = False
        self.person_too_long_alerted = False
        self.alerts = []

    def update(self, objects, current_time):
        has_car = any(obj.get('class_name') == 'car' for obj in objects)
        has_person = any(obj.get('class_name') == 'person' for obj in objects)

        if has_person and not has_car:
            if self.person_without_car_start_time is None:
                self.person_without_car_start_time = current_time
            elif current_time - self.person_without_car_start_time >= self.person_without_car_delay and not self.person_without_car_alerted:
                self._add_alert("Человек появился без автомобиля", current_time)
                self.person_without_car_alerted = True
        else:
            self.person_without_car_start_time = None
            self.person_without_car_alerted = False

        if has_car and not self.car_present:
            self.car_present = True
            self.car_appearance_time = current_time
        if not has_car and self.car_present:
            self.car_present = False
            self.car_appearance_time = None

        if has_person and not self.person_present:
            self.person_present = True
            self.person_appearance_time = current_time
        if not has_person and self.person_present:
            self.person_present = False
            self.person_appearance_time = None

        if self.person_present and self.person_appearance_time:
            pt = current_time - self.person_appearance_time
            if pt > self.max_person_time and not self.person_too_long_alerted:
                self._add_alert(f"Человек в кадре {int(pt)}с", current_time)
                self.person_too_long_alerted = True

        return self.get_alerts()

    def _add_alert(self, message, current_time):
        self.alerts.append({'type': 'scenario_violation', 'time': current_time, 'message': message})

    def get_alerts(self):
        alerts = self.alerts.copy()
        self.alerts.clear()
        return alerts

    def reset(self):
        self.car_present = False
        self.person_present = False
        self.car_appearance_time = None
        self.person_appearance_time = None
        self.car_abandoned_alerted = False
        self.person_too_long_alerted = False
        self.person_without_car_start_time = None
        self.person_without_car_alerted = False
        self.alerts.clear()