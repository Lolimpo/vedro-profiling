import time

import vedro


class Scenario(vedro.Scenario):
    subject = "Basic vedro test scenario"

    def given_something(self):
        pass

    def when_doing_some_work(self):
        for _ in range(10_000):
            time.sleep(0.001)

    def then_it_should_return_expected_result(self):
        assert True
