import time

import httpx
import vedro


class Scenario(vedro.Scenario):
    subject = "Base test scenario"

    def given_encoded_string(self):
        self.encoded = "YmFuYW5h"

    def when_user_decodes_string(self):
        self.response = httpx.get(f"https://httpbin.org/base64/{self.encoded}")
        time.sleep(10)

    def then_it_should_return_decoded_string(self):
        assert self.response.text == "banana"
