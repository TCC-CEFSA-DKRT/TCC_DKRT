import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import app as connector_app


def _seed(scenario, model):
    captured = {}

    def fake_orion_request(method, url, json=None, **kwargs):
        captured["entity"] = json

        class Resp:
            status_code = 201
            text = ""

            def json(self):
                return {}

        return Resp()

    with patch.object(connector_app, "orion_request", fake_orion_request):
        connector_app.seed_dkrt(
            scenario=scenario,
            model=model,
            authorization=f"Bearer {connector_app.SHARED_TOKEN}",
        )
    return captured["entity"]


def demo():
    weather_1 = _seed(1, "weather")
    assert "location" in weather_1
    assert weather_1["dateObserved"]["value"]

    weather_3 = _seed(3, "weather")
    assert "location" in weather_3
    assert "dateObserved" not in weather_3

    street_1 = _seed(1, "streetlight")
    assert "location" in street_1 and "status" in street_1

    street_3 = _seed(3, "streetlight")
    assert "location" in street_3 and "status" in street_3
    assert "powerState" not in street_3

    print("OK")


if __name__ == "__main__":
    demo()
